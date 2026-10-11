import datetime as dt
import json
import os
import socket
import struct
import threading

from .engine import get_engine
from .protocol import MAX_ADAPTER, MAX_FRAME, decode_array_if_complete, pack_frame, rename_vendor, strict_loads, valid_payload, valid_reading


def _listener(port, handler, label):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(64)
    print(f"{label} listening on 127.0.0.1:{port}", flush=True)
    while True:
        try:
            client, _ = server.accept()
        except OSError:
            break
        threading.Thread(target=handler, args=(client,), daemon=True).start()


def _recv_exact(sock, size):
    parts = bytearray()
    while len(parts) < size:
        data = sock.recv(size - len(parts))
        if not data:
            return None
        parts.extend(data)
    return bytes(parts)


def _ai_client(client):
    with client:
        while True:
            header = _recv_exact(client, 4)
            if header is None:
                return
            size = struct.unpack(">I", header)[0]
            if size > MAX_FRAME:
                return
            raw = _recv_exact(client, size)
            if raw is None:
                return
            try:
                payload = strict_loads(raw.decode("utf-8"))
                if valid_payload(payload):
                    get_engine().process(payload)
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError, OverflowError) as exc:
                print(f"AI server ignored malformed frame: {type(exc).__name__}", flush=True)


def run_ai():
    get_engine()  # Capture the process start session and establish model readiness before listening.
    _listener(65432, _ai_client, "AI server")


def _forward(readings):
    payload = {"sim_date": dt.date.today().isoformat(), "readings": readings}
    frame = pack_frame(payload)
    for attempt in range(2):
        try:
            with socket.create_connection(("127.0.0.1", 65432), timeout=3) as client:
                client.sendall(frame)
            return
        except OSError as exc:
            if attempt:
                print(f"Adapter dropped batch after retry: {type(exc).__name__}", flush=True)


def _adapter_client(client):
    buffer = bytearray()
    client.settimeout(5)
    with client:
        while True:
            try:
                chunk = client.recv(min(65536, MAX_ADAPTER + 1 - len(buffer)))
            except socket.timeout:
                print("Adapter discarded timed-out JSON", flush=True)
                return
            except OSError:
                return
            if not chunk:
                try:
                    parsed = decode_array_if_complete(buffer)
                except ValueError:
                    print("Adapter discarded malformed JSON", flush=True)
                    return
                if parsed is not None:
                    _process_adapter(parsed)
                else:
                    print("Adapter discarded incomplete JSON", flush=True)
                return
            buffer.extend(chunk)
            if len(buffer) > MAX_ADAPTER:
                print("Adapter discarded oversized JSON", flush=True)
                return
            try:
                parsed = decode_array_if_complete(buffer)
            except ValueError:
                print("Adapter discarded malformed JSON", flush=True)
                return
            if parsed is not None:
                _process_adapter(parsed)
                return


def _process_adapter(parsed):
    if not isinstance(parsed, list):
        return
    valid = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        mapped = rename_vendor(item)
        if valid_reading(mapped):
            valid.append(mapped)
    if valid:
        _forward(valid)


def run_adapter():
    _listener(65431, _adapter_client, "Device adapter")


def simulator():
    import random
    n = int(os.environ["LIVE_N_PATIENTS"])
    interval = float(os.environ["LIVE_TICK_SECONDS"])
    critical_until = {}
    while True:
        now = dt.datetime.now()
        readings = []
        for pid in range(1, n + 1):
            state = random.random()
            if state < 0.015 and critical_until.get(pid, 0) < now.timestamp():
                critical_until[pid] = now.timestamp() + random.randint(2, 4) * interval
            critical = critical_until.get(pid, 0) >= now.timestamp()
            unhealthy = critical or random.random() < 0.13
            hr = random.gauss(130 if critical else 104 if unhealthy else 72, 8)
            sbp = random.gauss(175 if critical else 145 if unhealthy else 120, 10)
            spo2 = random.gauss(84 if critical else 93 if unhealthy else 97, 2)
            readings.append({"patient_id": pid, "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                "heart_rate": None if random.random() < .04 else round(hr, 1),
                "systolic_bp": None if random.random() < .04 else round(sbp, 1),
                "diastolic_bp": round(random.gauss(80, 5), 1), "body_temp": round(random.gauss(36.8, .4), 1),
                "spo2": None if random.random() < .04 else round(spo2, 1), "activity": random.choice([0, 1, 2, 3, 4])})
        try:
            with socket.create_connection(("127.0.0.1", 65432), timeout=3) as client:
                client.sendall(pack_frame({"sim_date": now.date().isoformat(), "readings": readings}))
        except OSError as exc:
            print(f"Simulator reconnecting after: {type(exc).__name__}", flush=True)
        threading.Event().wait(interval)
