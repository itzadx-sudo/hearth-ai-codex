import datetime as dt
import json
import math
import struct

MAX_FRAME = 10 * 1024 * 1024
MAX_ADAPTER = 1024 * 1024
MAX_PID = 2**63 - 1
VITALS = ("heart_rate", "systolic_bp", "diastolic_bp", "body_temp", "spo2")
RENAME = {
    "vendor_bpm": "heart_rate", "vendor_oxygen": "spo2", "vendor_movement": "activity",
    "alt_temp": "body_temp", "bed_sys": "systolic_bp", "bed_dia": "diastolic_bp",
}


def _reject_constant(_value):
    raise ValueError("non-standard JSON constant")


def strict_loads(data):
    return json.loads(data, parse_constant=_reject_constant)


def valid_pid(value):
    return type(value) is int and 1 <= value <= MAX_PID


def valid_timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return parsed.strftime("%Y-%m-%d %H:%M:%S") == value
    except ValueError:
        return False


def valid_reading(reading):
    return (isinstance(reading, dict) and valid_pid(reading.get("patient_id"))
            and valid_timestamp(reading.get("timestamp")))


def normalized_reading(reading):
    out = dict(reading)
    for key in VITALS:
        value = reading.get(key)
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            out[key] = None
            continue
        try:
            value = float(value)
        except (OverflowError, ValueError):
            out[key] = None
            continue
        out[key] = value if math.isfinite(value) else None
    return out


def valid_payload(payload):
    return (isinstance(payload, dict) and isinstance(payload.get("sim_date"), str)
            and bool(payload["sim_date"]) and isinstance(payload.get("readings"), list)
            and bool(payload["readings"]))


def pack_frame(payload):
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    return struct.pack(">I", len(data)) + data


def rename_vendor(reading):
    renamed = {}
    for key, value in reading.items():
        renamed[RENAME.get(key, key)] = value
    return renamed


def decode_array_if_complete(buffer):
    """Return parsed top-level array as soon as its complete JSON value is buffered."""
    decoder = json.JSONDecoder(parse_constant=_reject_constant)
    try:
        text = buffer.decode("utf-8")
        start = len(text) - len(text.lstrip())
        if start == len(text):
            return None
        if text[start] != "[":
            raise ValueError("top-level JSON must be an array")
        value, end = decoder.raw_decode(text, start)
        if not isinstance(value, list):
            raise ValueError("top-level JSON must be an array")
        if text[end:].strip():
            raise ValueError("trailing data")
        return value
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
