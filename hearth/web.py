import datetime as dt
import json
import os
import re
from functools import wraps

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for

from .config import db_path
from .database import connect, current_session, json_dump
from .engine import FEATURES, STATUS, get_engine
from .protocol import MAX_PID, valid_pid
from .security import bootstrap_admin, hash_password, verify_password


EMPTY_LIVE = {"session_id": None, "summary": {}, "predictions": [], "tick_series": [], "tick_stats": {},
              "message": "No live session found. Waiting for data..."}
EMPTY_OVERVIEW = {"live_mode": True, "session_id": None, "patients": [], "tick_stats": {}, "day_summary": {},
                  "leaderboard": [], "recent_alerts": [], "summary": {}, "system_health": {}}
VITALS = ("heart_rate", "systolic_bp", "diastolic_bp", "body_temp", "spo2")


def _safe_json(value, default=None):
    try:
        return json.loads(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def _principal():
    username = session.get("username")
    if not username:
        return None
    with connect() as conn:
        row = conn.execute("SELECT username,role,display_name FROM users WHERE username=?", (username,)).fetchone()
        if not row:
            session.clear()
            return None
        obj = dict(row)
        obj["patients"] = [r[0] for r in conn.execute("SELECT patient_id FROM assignments WHERE username=? ORDER BY patient_id", (username,))] if row["role"] == "guardian" else []
        return obj


def _auth_required():
    user = _principal()
    if not user:
        return None, (jsonify(error="Unauthorized"), 401)
    return user, None


def _admin_required():
    user, error = _auth_required()
    if error:
        return None, error
    if user["role"] != "admin":
        return None, (jsonify(error="Unauthorized"), 403)
    return user, None


def _allowed_ids(user):
    return None if user["role"] == "admin" else set(user["patients"])


def _rows_for_session(conn, sid, allowed):
    rows = conn.execute("SELECT * FROM ticks WHERE session_id=? ORDER BY tick,patient_id", (sid,)).fetchall()
    return [r for r in rows if allowed is None or r["patient_id"] in allowed]


def _patient_rows(rows):
    latest = {}
    for row in rows:
        latest[row["patient_id"]] = row
    return latest


def _latest_predictions(conn, sid, allowed):
    rows = conn.execute("SELECT * FROM predictions WHERE session_id=? ORDER BY tick DESC", (sid,)).fetchall()
    latest = {}
    for row in rows:
        if row["patient_id"] not in latest and (allowed is None or row["patient_id"] in allowed):
            latest[row["patient_id"]] = row
    return latest


def _patient_json(row, pred=None):
    activity = _safe_json(row["activity"])
    return {"patient_id": row["patient_id"], "session_id": row["session_id"], "tick": row["tick"],
        "tick_time": row["tick_time"], "status": row["status"], "confidence": row["confidence"],
        **{key: row[key] for key in VITALS}, "activity": activity,
        "attention_weights": row["attention"], "risk_score": pred["risk_score"] if pred else 0.0,
        "risk_label": pred["risk_label"] if pred else "—", "worst_status": row["status"],
        "sim_date": row["tick_time"], "avg_heart_rate": row["heart_rate"],
        "avg_systolic": row["systolic_bp"], "avg_diastolic": row["diastolic_bp"],
        "avg_temp": row["body_temp"], "avg_spo2": row["spo2"]}


def _tick_stats(rows, tick):
    group = [r for r in rows if r["tick"] == tick]
    counts = {s: sum(1 for r in group if r["status"] == s) for s in STATUS}
    result = {"tick": tick, "patient_count": len(group), "status_counts": counts}
    for key in VITALS:
        values = [r[key] for r in group if r[key] is not None]
        result[{"heart_rate": "avg_heart_rate", "systolic_bp": "avg_systolic", "diastolic_bp": "avg_diastolic", "body_temp": "avg_temp", "spo2": "avg_spo2"}[key]] = round(sum(values) / len(values), 2) if values else None
    return result


def _series(rows, limit=40):
    ticks = sorted({r["tick"] for r in rows})[-limit:]
    output = []
    for tick in ticks:
        group = [r for r in rows if r["tick"] == tick]
        counts = {s: sum(1 for r in group if r["status"] == s) for s in STATUS}
        output.append({"tick": tick, "tick_time": group[0]["tick_time"], **counts})
    return output


def _summary(rows, sid, preds):
    latest = _patient_rows(rows)
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUS}
    high = sum(1 for p in preds.values() if p["risk_score"] >= .5)
    return {"session_id": sid, "total_ticks": len({r["tick"] for r in rows}),
            "total_patients": len(latest), "status_counts": counts, "high_risk_patients": high}


def _alert_rows(conn, allowed, limit=200):
    rows = conn.execute("SELECT * FROM ticks ORDER BY tick_time DESC").fetchall()
    latest_critical = {}
    for row in rows:
        pid = row["patient_id"]
        if (allowed is None or pid in allowed) and row["status"] == "Critical" and pid not in latest_critical:
            latest_critical[pid] = row
    critical = sorted(latest_critical.values(), key=lambda r: r["tick_time"], reverse=True)[:100]
    pred_rows = conn.execute("SELECT * FROM predictions WHERE risk_label='HIGH RISK' ORDER BY computed_at_time DESC").fetchall()
    latest_pred = {}
    for row in pred_rows:
        if (allowed is None or row["patient_id"] in allowed) and row["patient_id"] not in latest_pred:
            latest_pred[row["patient_id"]] = row
    alerts = []
    for r in critical:
        alerts.append({"id": None, "patient_id": r["patient_id"], "alert_type": "critical", "type": "critical",
            "timestamp": r["tick_time"], "sim_date": r["tick_time"], "confidence": r["confidence"], "risk_label": None, "top_factors": []})
    for r in latest_pred.values():
        alerts.append({"id": None, "patient_id": r["patient_id"], "alert_type": "predictive", "type": "predictive",
            "timestamp": r["computed_at_time"], "sim_date": r["computed_at_time"], "confidence": r["risk_score"],
            "risk_label": r["risk_label"], "top_factors": _safe_json(r["top_factors"], [])})
    return sorted(alerts, key=lambda x: x["timestamp"], reverse=True)[:limit]


def _system():
    try:
        engine = get_engine()
        loaded = bool(engine.ready)
    except Exception:
        loaded = False
    with connect() as conn:
        sid = current_session(conn)
        ticks = conn.execute("SELECT COUNT(DISTINCT tick) FROM ticks WHERE session_id=?", (sid,)).fetchone()[0] if sid else 0
    size = round(os.path.getsize(db_path()) / 1048576, 2) if os.path.exists(db_path()) else 0.0
    return {"total_patients": 0, "days_processed": 0,
            "model_status": "loaded" if loaded else "missing", "predictor_status": "loaded" if loaded else "missing",
            "db_size_mb": size, "live_ticks": ticks, "live_session": sid or "—", "live_size_mb": size}


def create_app(config):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = config["session_key"]
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict", SESSION_COOKIE_SECURE=False)
    expected_origin = f"http://127.0.0.1:{config['port']}"

    @app.before_request
    def origin_first():
        if request.path.startswith("/api/") and request.method == "POST":
            origins = request.headers.getlist("Origin")
            if len(origins) != 1 or origins[0] != expected_origin:
                return jsonify(error="Invalid origin"), 403

    @app.get("/")
    def root():
        if _principal():
            return render_template("dashboard.html")
        return redirect("/landing")

    @app.get("/landing")
    def landing():
        return render_template("landing.html")

    @app.get("/dashboard")
    def dashboard():
        if not _principal():
            return redirect("/landing")
        return render_template("dashboard.html")

    @app.post("/api/signup")
    def signup():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not data.get("username") or not data.get("password"):
            return jsonify(error="Missing credentials"), 400
        username, password = data["username"], data["password"]
        if not isinstance(username, str) or not isinstance(password, str) or len(username) > 80 or len(password) < 1:
            return jsonify(error="Invalid credentials"), 400
        role = data.get("role", "guardian")
        if role != "guardian":
            return jsonify(error="Only guardian signup is allowed"), 403
        salt, hashed = hash_password(password)
        try:
            with connect() as conn:
                conn.execute("INSERT INTO users(username,password_hash,salt,role) VALUES(?,?,?,'guardian')", (username, hashed, salt))
        except Exception:
            return jsonify(error="Username already exists"), 400
        return jsonify(message="User created")

    @app.post("/api/login")
    def login():
        data = request.get_json(silent=True)
        username = data.get("username") if isinstance(data, dict) else None
        password = data.get("password") if isinstance(data, dict) else None
        if not isinstance(username, str) or not isinstance(password, str):
            return jsonify(error="Invalid credentials"), 401
        with connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not row or not verify_password(password, row["salt"], row["password_hash"]):
            return jsonify(error="Invalid credentials"), 401
        session.clear()
        session["username"] = username
        return jsonify(message="Logged in", user={"username": username, "role": row["role"], "display_name": row["display_name"]})

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify(message="Logged out")

    @app.get("/api/auth_status")
    def auth_status():
        user = _principal()
        if not user:
            return jsonify(logged_in=False)
        return jsonify(logged_in=True, username=user["username"], display_name=user["display_name"], role=user["role"], patients=user["patients"])

    @app.post("/api/update_name")
    def update_name():
        user, error = _auth_required()
        if error:
            return error
        data = request.get_json(silent=True)
        name = data.get("display_name") if isinstance(data, dict) else None
        if not isinstance(name, str):
            return jsonify(error="Invalid display name"), 400
        name = name.strip()
        if not 1 <= len(name) <= 80 or any(ord(c) <= 31 or ord(c) == 127 for c in name):
            return jsonify(error="Invalid display name"), 400
        with connect() as conn:
            conn.execute("UPDATE users SET display_name=? WHERE username=?", (name, user["username"]))
        return jsonify(message="Name updated", display_name=name)

    @app.post("/api/assign_patient")
    def assign_patient():
        user, error = _admin_required()
        if error:
            return error
        data = request.get_json(silent=True)
        pid = data.get("patient_id") if isinstance(data, dict) else None
        guardian = data.get("guardian_username") if isinstance(data, dict) else None
        if not valid_pid(pid):
            return jsonify(error="Invalid patient_id"), 400
        with connect() as conn:
            row = conn.execute("SELECT role FROM users WHERE username=?", (guardian,)).fetchone() if isinstance(guardian, str) else None
            if not row or row["role"] != "guardian":
                return jsonify(error="Unknown guardian"), 400
            conn.execute("INSERT OR IGNORE INTO assignments(username,patient_id) VALUES(?,?)", (guardian, pid))
        return jsonify(message="Patient assigned")

    @app.get("/api/guardians")
    def guardians():
        _, error = _admin_required()
        if error:
            return error
        with connect() as conn:
            return jsonify([r[0] for r in conn.execute("SELECT username FROM users WHERE role='guardian' ORDER BY username")])

    @app.get("/api/patients")
    def patients():
        user, error = _auth_required()
        if error:
            return error
        allowed = _allowed_ids(user)
        with connect() as conn:
            sid = current_session(conn)
            if not sid:
                return jsonify([])
            rows = _rows_for_session(conn, sid, allowed)
            latest = _patient_rows(rows)
            preds = _latest_predictions(conn, sid, allowed)
            result = [_patient_json(r, preds.get(pid)) for pid, r in latest.items()]
        result.sort(key=lambda p: p["risk_score"], reverse=True)
        return jsonify(result)

    @app.get("/api/patients/<pid>")
    def patient_detail_legacy(pid):
        user, error = _auth_required()
        if error:
            return error
        parsed = int(pid) if re.fullmatch(r"[0-9]+", pid) else -1
        if user["role"] == "guardian" and parsed not in user["patients"]:
            return jsonify({}), 403
        return _detail(parsed)

    @app.get("/api/patient/<pid>")
    def patient_detail(pid):
        user, error = _auth_required()
        if error:
            return error
        parsed = int(pid) if re.fullmatch(r"[0-9]+", pid) else -1
        if user["role"] == "guardian" and parsed not in user["patients"]:
            return jsonify(error="Unauthorized", found=False), 403
        return _detail(parsed, found_contract=True)

    def _detail(pid, found_contract=False):
        if not 1 <= pid <= MAX_PID:
            return (jsonify(error="Not found", found=False), 404) if found_contract else (jsonify(error="Not found"), 404)
        with connect() as conn:
            sid = current_session(conn)
            if not sid:
                return (jsonify(error="Not found", found=False), 404) if found_contract else (jsonify(error="Not found"), 404)
            rows = conn.execute("SELECT * FROM ticks WHERE session_id=? AND patient_id=? ORDER BY tick", (sid, pid)).fetchall()
            if not rows:
                return (jsonify(error="Not found", found=False), 404) if found_contract else (jsonify(error="Not found"), 404)
            latest = rows[-1]
            pred = conn.execute("SELECT * FROM predictions WHERE session_id=? AND patient_id=? ORDER BY tick DESC LIMIT 1", (sid, pid)).fetchone()
            history = [{"tick": r["tick"], "tick_time": r["tick_time"], "status": r["status"], "confidence": r["confidence"], **{k: r[k] for k in VITALS}, "activity": _safe_json(r["activity"])} for r in rows]
            prediction = ({"computed_at_tick": pred["tick"], "computed_at_time": pred["computed_at_time"], "patient_id": pid,
                           "risk_label": pred["risk_label"], "risk_score": pred["risk_score"], "top_factors": _safe_json(pred["top_factors"], [])} if pred else None)
            if found_contract:
                p = _patient_json(latest, pred)
                p.update(attention=_safe_json(latest["attention"], None), history=history, prediction=prediction)
                return jsonify(found=True, session_id=sid, patient=p)
            dates = [r["tick_time"] for r in rows]
            current = {"worst_status": latest["status"], "sim_date": latest["tick_time"], "confidence": latest["confidence"]}
            aliases = dict(zip(("avg_heart_rate", "avg_systolic", "avg_diastolic", "avg_temp", "avg_spo2"), (latest[k] for k in VITALS)))
            current.update(aliases)
            trend = {"dates": dates, "heart_rate": [r["heart_rate"] for r in rows], "systolic_bp": [r["systolic_bp"] for r in rows], "body_temp": [r["body_temp"] for r in rows], "spo2": [r["spo2"] for r in rows]}
            return jsonify(patient_id=pid, current_status=current, latest_prediction=prediction, context_metrics={}, vitals_trend=trend, history=history[-20:])

    @app.get("/api/live")
    def live():
        user, error = _auth_required()
        if error:
            return error
        allowed = _allowed_ids(user)
        with connect() as conn:
            sid = current_session(conn)
            rows = _rows_for_session(conn, sid, allowed) if sid else []
            if not rows:
                return jsonify(EMPTY_LIVE)
            preds = _latest_predictions(conn, sid, allowed)
        summary = _summary(rows, sid, preds)
        patients = _patient_rows(rows)
        tick = max(r["tick"] for r in rows)
        predictions = sorted(({"computed_at_tick": p["tick"], "computed_at_time": p["computed_at_time"], "patient_id": pid,
            "risk_label": p["risk_label"], "risk_score": p["risk_score"], "top_factors": p["top_factors"]} for pid, p in preds.items()), key=lambda p: p["risk_score"], reverse=True)[:200]
        return jsonify(session_id=sid, summary=summary, predictions=predictions, tick_series=_series(rows), tick_stats=_tick_stats(rows, tick))

    @app.get("/api/overview")
    def overview():
        user, error = _auth_required()
        if error:
            return error
        allowed = _allowed_ids(user)
        with connect() as conn:
            sid = current_session(conn)
            rows = _rows_for_session(conn, sid, allowed) if sid else []
            if not rows:
                output = dict(EMPTY_OVERVIEW)
                if user["role"] == "admin":
                    output["system_health"] = _system()
                return jsonify(output)
            preds = _latest_predictions(conn, sid, allowed)
            alerts = _alert_rows(conn, allowed, 12)
        latest = _patient_rows(rows)
        patients = [_patient_json(row, preds.get(pid)) for pid, row in latest.items()]
        patients.sort(key=lambda p: p["risk_score"], reverse=True)
        tick = max(r["tick"] for r in rows)
        summary = _summary(rows, sid, preds)
        system = _system() if user["role"] == "admin" else {}
        # Overview alerts are based on latest current-session status and current-session latest predictions.
        current_alerts = []
        for pid, row in latest.items():
            if row["status"] == "Critical":
                current_alerts.append({"id": None, "patient_id": pid, "alert_type": "critical", "type": "critical", "timestamp": row["tick_time"], "sim_date": row["tick_time"], "confidence": row["confidence"], "risk_label": None, "top_factors": []})
            pred = preds.get(pid)
            if pred and pred["risk_score"] >= .5:
                current_alerts.append({"id": None, "patient_id": pid, "alert_type": "predictive", "type": "predictive", "timestamp": pred["computed_at_time"], "sim_date": pred["computed_at_time"], "confidence": pred["risk_score"], "risk_label": pred["risk_label"], "top_factors": _safe_json(pred["top_factors"], [])})
        current_alerts.sort(key=lambda a: a["timestamp"], reverse=True)
        leaderboard = sorted(({"patient_id": pid, "risk_score": p["risk_score"], "risk_label": p["risk_label"], "top_factors": _safe_json(p["top_factors"], [])} for pid, p in preds.items()), key=lambda p: p["risk_score"], reverse=True)[:10]
        stats = _tick_stats(rows, tick)
        return jsonify(live_mode=True, session_id=sid, patients=patients, tick_stats=stats, day_summary=stats, leaderboard=leaderboard,
                       recent_alerts=current_alerts[:12], system_health=system, summary=summary)

    @app.get("/api/alerts")
    def alerts():
        user, error = _auth_required()
        if error:
            return error
        with connect() as conn:
            return jsonify(_alert_rows(conn, _allowed_ids(user)))

    @app.get("/api/system")
    def system():
        _, error = _admin_required()
        if error:
            return error
        return jsonify(_system())

    @app.get("/api/training_status")
    def training_status():
        _, error = _admin_required()
        if error:
            return error
        return jsonify(training=False, message="Training is outside the live-mode demo scope.")

    @app.post("/api/retrain")
    def retrain():
        _, error = _admin_required()
        if error:
            return error
        return jsonify(error="Training is not available in Stage A"), 501

    return app


def bootstrap_from_environment(config):
    if config["admin_user"] is not None:
        bootstrap_admin(config["admin_user"], config["admin_pass"])
