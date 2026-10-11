import json
import os
import socket
import struct
import subprocess
import sys
import time

import pytest

from hearth.database import initialize
from hearth.engine import InferenceEngine
from hearth.protocol import decode_array_if_complete, normalized_reading, valid_reading
from hearth.web import create_app


@pytest.fixture
def app_db(tmp_path, monkeypatch):
    monkeypatch.setenv("HEARTH_DATA_DIR", str(tmp_path))
    initialize()
    app = create_app({"session_key": "self-test-only-session-key", "port": 8050, "admin_user": None, "admin_pass": None})
    app.config.update(TESTING=True)
    return app


def test_structural_ids_and_vitals_normalization():
    reading = {"patient_id": 1, "timestamp": "2026-10-11 12:30:01", "heart_rate": "abc",
               "systolic_bp": True, "diastolic_bp": 1e400, "body_temp": 10**400, "spo2": 92.5}
    assert valid_reading(reading)
    normalized = normalized_reading(reading)
    assert [normalized[k] for k in ("heart_rate", "systolic_bp", "diastolic_bp", "body_temp", "spo2")] == [None, None, None, None, 92.5]
    assert not valid_reading({**reading, "patient_id": 1.0})
    assert not valid_reading({**reading, "patient_id": True})
    assert not valid_reading({**reading, "patient_id": 2**63})
    assert not valid_reading({**reading, "timestamp": "2026-02-30 12:00:00"})


def test_bad_frames_do_not_advance_ticks_and_activity_defaults_to_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("HEARTH_DATA_DIR", str(tmp_path))
    initialize()
    engine = InferenceEngine()
    base = {"patient_id":1,"timestamp":"2026-10-11 12:30:00","heart_rate":72}
    for payload in ({"sim_date":"2026-10-11","readings":[{**base,"patient_id":1.0}]},
                    {"sim_date":"2026-10-11","readings":[{**base,"patient_id":2**63}]}):
        assert not engine.process(payload)
    assert engine.tick == 0
    from hearth.engine import _activity
    assert _activity(None) == _activity(True) == _activity("unknown") == 0
    assert _activity("active") == 3


def test_segmented_adapter_array_decode():
    data = b'  [{"patient_id":1,'
    assert decode_array_if_complete(data) is None
    assert decode_array_if_complete(data + b'"timestamp":"2026-10-11 00:00:00"}]  ') == [
        {"patient_id": 1, "timestamp": "2026-10-11 00:00:00"}]
    with pytest.raises(ValueError):
        decode_array_if_complete(b'[{"a":1}] trailing')


def test_csrf_auth_assignment_and_empty_contracts(app_db):
    client = app_db.test_client()
    assert client.get("/").status_code == 302
    assert client.get("/api/live").status_code == 401
    assert client.post("/api/signup", json={"username":"guard", "password":"secret", "role":"admin"},
                       headers={"Origin":"http://127.0.0.1:8050"}).status_code == 403
    assert client.post("/api/signup", json={"username":"guard", "password":"secret"}).status_code == 403
    assert client.post("/api/signup", json={"username":"guard", "password":"secret"},
                       headers={"Origin":"http://localhost:8050"}).status_code == 403
    assert client.post("/api/signup", json={"username":"guard", "password":"secret"},
                       headers={"Origin":"http://127.0.0.1:8050"}).status_code == 200
    with client.session_transaction() as s:
        s["username"] = "guard"
    empty = client.get("/api/live").get_json()
    assert empty == {"session_id":None,"summary":{},"predictions":[],"tick_series":[],"tick_stats":{},
                     "message":"No live session found. Waiting for data..."}
    assert client.get("/api/overview").get_json() == {"live_mode":True,"session_id":None,"patients":[],"tick_stats":{},
        "day_summary":{},"leaderboard":[],"recent_alerts":[],"summary":{},"system_health":{}}
    assert client.get("/api/logout").status_code == 405


def test_guardian_assignment_filter_and_strict_assignment_ids(app_db):
    from hearth.database import connect
    from hearth.security import bootstrap_admin
    bootstrap_admin("admin","temporary-admin-test-password")
    client=app_db.test_client()
    assert client.post("/api/signup",json={"username":"assigned","password":"secret"},
        headers={"Origin":"http://127.0.0.1:8050"}).status_code==200
    with client.session_transaction() as s: s["username"]="admin"
    for bad in (1.0,True,0,-1,2**63):
        response=client.post("/api/assign_patient",json={"guardian_username":"assigned","patient_id":bad},
            headers={"Origin":"http://127.0.0.1:8050"})
        assert response.status_code==400
    assert client.post("/api/assign_patient",json={"guardian_username":"assigned","patient_id":1},
        headers={"Origin":"http://127.0.0.1:8050"}).status_code==200
    with connect() as conn:
        for pid in (1,2):
            conn.execute("INSERT INTO ticks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",("20261011_120000",1,"2026-10-11 12:00:00",pid,"Healthy",.8,72,120,80,36.6,97,"0","{}"))
    with client.session_transaction() as s: s["username"]="assigned"
    patients=client.get("/api/patients").get_json()
    assert [p["patient_id"] for p in patients]==[1]
    live=client.get("/api/live").get_json()
    assert live["summary"]["total_patients"]==1 and live["summary"]["status_counts"]["Healthy"]==1
    assert client.get("/api/patient/2").status_code==403
    assert client.get("/api/system").status_code==403


def test_classification_persists_tick_and_seven_tick_prediction(tmp_path, monkeypatch):
    monkeypatch.setenv("HEARTH_DATA_DIR", str(tmp_path))
    initialize()
    engine = InferenceEngine()
    reading = {"patient_id": 7, "timestamp":"2026-10-11 12:30:01", "heart_rate":72,
        "systolic_bp":120,"diastolic_bp":80,"body_temp":36.6,"spo2":97,"activity":0}
    for i in range(7):
        assert engine.process({"sim_date":"2026-10-11","readings":[{**reading,"timestamp":f"2026-10-11 12:30:0{i}",
            "heart_rate":"abc" if i == 6 else 72,"systolic_bp":True if i == 6 else 120,
            "diastolic_bp":1e400 if i == 6 else 80,"body_temp":10**400 if i == 6 else 36.6}]})
    from hearth.database import connect
    with connect() as conn:
        rows = conn.execute("SELECT tick,heart_rate FROM ticks WHERE patient_id=7 ORDER BY tick").fetchall()
        preds = conn.execute("SELECT COUNT(*) FROM predictions WHERE patient_id=7").fetchone()[0]
    assert len(rows) == 7 and rows[0]["tick"] == 1 and rows[-1]["heart_rate"] is None
    assert preds == 1
    from hearth.security import bootstrap_admin
    bootstrap_admin("reader","temporary-reader-test-password")
    client=create_app({"session_key":"self-test-only-session-key","port":8050,"admin_user":None,"admin_pass":None}).test_client()
    with client.session_transaction() as s: s["username"]="reader"
    first=client.get("/api/patients").get_json()[0]
    assert first["heart_rate"] is None and first["systolic_bp"] is None and first["diastolic_bp"] is None and first["body_temp"] is None


def test_shared_model_batch_interface():
    import torch
    from shared_model import load_model
    model=load_model()
    assert not model.training
    outputs=model(torch.zeros((2,8),dtype=torch.float32))
    assert [tuple(value.shape) for value in outputs]==[(2,3),(2,1),(2,8)]


def test_environment_validation_rejects_empty_and_forbidden_forms(tmp_path):
    base = os.environ.copy()
    base.update({"HEARTH_DATA_DIR":str(tmp_path),"HEARTH_SIMULATE":"0"})
    base.pop("HEARTH_SESSION_KEY", None)
    cases = [({"LIVE_N_PATIENTS":""}, "LIVE_N_PATIENTS"), ({"LIVE_N_PATIENTS":"+2"}, "LIVE_N_PATIENTS"),
             ({"LIVE_N_PATIENTS":"2_0"}, "LIVE_N_PATIENTS"), ({"LIVE_N_PATIENTS":"501"}, "LIVE_N_PATIENTS"),
             ({"LIVE_TICK_SECONDS":"1e1"}, "LIVE_TICK_SECONDS"), ({"LIVE_TICK_SECONDS":""}, "LIVE_TICK_SECONDS"),
             ({"LIVE_TICK_SECONDS":"NaN"}, "LIVE_TICK_SECONDS"), ({"LIVE_TICK_SECONDS":"-1"}, "LIVE_TICK_SECONDS"),
             ({"LIVE_TICK_SECONDS":"30.1"}, "LIVE_TICK_SECONDS"), ({"HEARTH_DASHBOARD_PORT":"70000"}, "HEARTH_DASHBOARD_PORT"),
             ({"HEARTH_DASHBOARD_PORT":"65431"}, "HEARTH_DASHBOARD_PORT"), ({"HEARTH_DASHBOARD_PORT":""}, "HEARTH_DASHBOARD_PORT"),
             ({"HEARTH_SESSION_KEY":""}, "HEARTH_SESSION_KEY")]
    for update, expected in cases:
        env=base.copy();env.update(update)
        run=subprocess.run([sys.executable,"-m","hearth.launch","validate"],cwd=os.getcwd(),env=env,capture_output=True,text=True)
        assert run.returncode != 0 and expected in run.stderr


def test_launch_readiness_shutdown_and_immediate_rebind(tmp_path):
    shim=tmp_path/"bin";shim.mkdir()
    (shim/"python").symlink_to(sys.executable)
    env=os.environ.copy();env.update({"PATH":str(shim)+os.pathsep+env.get("PATH",""),"HEARTH_DATA_DIR":str(tmp_path/"data"),
        "HEARTH_ADMIN_USER":"test-admin","HEARTH_ADMIN_PASS":"temporary-test-password","HEARTH_SIMULATE":"0",
        "HEARTH_DASHBOARD_PORT":"18050","HEARTH_SESSION_KEY":"temporary-test-session-key"})
    proc=subprocess.Popen(["./start.sh"],cwd=os.getcwd(),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    try:
        deadline=time.monotonic()+30
        ready=False
        while time.monotonic()<deadline:
            try:
                import urllib.request
                with urllib.request.urlopen("http://127.0.0.1:18050/api/auth_status",timeout=.5) as response:
                    ready=response.status==200 and json.loads(response.read()).get("logged_in") is False
                if ready:
                    for port in (65431,65432):
                        with socket.create_connection(("127.0.0.1",port),timeout=.5): pass
                    break
            except Exception:
                time.sleep(.15)
        assert ready, "services did not become ready"
        assert (tmp_path/"data"/"hearth.db").exists()
        # Exercise the real segmented adapter with a payload close to its 1 MiB limit.
        payload=json.dumps([{"patient_id":41,"timestamp":"2026-10-11 12:30:01","vendor_bpm":73,
            "vendor_oxygen":96,"bed_sys":121,"bed_dia":81,"alt_temp":36.7,"vendor_movement":"active",
            "vendor_extension":"x"*900000}],separators=(",",":")).encode()
        with socket.create_connection(("127.0.0.1",65431),timeout=3) as client:
            client.sendall(payload[:37]);time.sleep(.08);client.sendall(payload[37:])
            client.settimeout(3);assert client.recv(1)==b""
        import sqlite3
        database=sqlite3.connect(tmp_path/"data"/"hearth.db")
        deadline=time.monotonic()+5
        stored=None
        while time.monotonic()<deadline:
            stored=database.execute("SELECT session_id,tick,heart_rate,activity FROM ticks WHERE patient_id=41").fetchone()
            if stored: break
            time.sleep(.1)
        database.close()
        assert stored and stored[1:3]==(1,73.0) and json.loads(stored[3])=="active"
        proc.terminate();proc.wait(timeout=8)
        assert proc.returncode == 0
        # Immediate TCP and HTTP bind checks after launcher exit.
        for port in (65431,65432):
            s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(("127.0.0.1",port));s.close()
        s=socket.socket();s.bind(("127.0.0.1",18050));s.close()
        # Restart with no new frame: the last persisted session remains visible.
        proc=subprocess.Popen(["./start.sh"],cwd=os.getcwd(),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            try:
                import urllib.request
                with urllib.request.urlopen("http://127.0.0.1:18050/api/auth_status",timeout=.5) as response:
                    assert response.status==200
                break
            except Exception: time.sleep(.15)
        from http.cookiejar import CookieJar
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        login=urllib.request.Request("http://127.0.0.1:18050/api/login",data=json.dumps({"username":"test-admin","password":"temporary-test-password"}).encode(),
            headers={"Content-Type":"application/json","Origin":"http://127.0.0.1:18050"},method="POST")
        with opener.open(login,timeout=3) as response: assert json.loads(response.read())["user"]["role"]=="admin"
        with opener.open("http://127.0.0.1:18050/api/system",timeout=3) as response:
            system=json.loads(response.read())
        assert system["model_status"]==system["predictor_status"]=="loaded"
        assert system["db_size_mb"]==system["live_size_mb"]
        with opener.open("http://127.0.0.1:18050/api/live",timeout=3) as response:
            live=json.loads(response.read())
        assert live["session_id"]==stored[0] and live["summary"]["total_ticks"]==1
        proc.terminate();proc.wait(timeout=8);assert proc.returncode==0
        # The optional simulator starts only when enabled and writes recurring ticks.
        env.update(HEARTH_SIMULATE="1",LIVE_N_PATIENTS="2",LIVE_TICK_SECONDS="0.5")
        proc=subprocess.Popen(["./start.sh"],cwd=os.getcwd(),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        database=sqlite3.connect(tmp_path/"data"/"hearth.db")
        deadline=time.monotonic()+20
        simulated=False
        while time.monotonic()<deadline:
            simulated=database.execute("SELECT COUNT(*) FROM ticks WHERE session_id<>?",(stored[0],)).fetchone()[0]>=2
            if simulated: break
            time.sleep(.2)
        database.close()
        assert simulated
        proc.terminate();proc.wait(timeout=8);assert proc.returncode==0
    finally:
        if proc.poll() is None:
            proc.kill();proc.wait(timeout=3)
