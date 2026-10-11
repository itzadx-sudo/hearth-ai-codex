import datetime as dt
import json
import math
import threading
from collections import defaultdict, deque

import numpy as np
import torch
from shared_model import load_model

from .database import connect, current_session, json_dump
from .protocol import VITALS, normalized_reading, valid_payload, valid_reading

FEATURES = ["heart_rate", "systolic_bp", "diastolic_bp", "body_temp", "spo2", "activity", "delta_hr", "delta_spo2"]
BOUNDS = {"heart_rate": (20, 220), "systolic_bp": (50, 280), "diastolic_bp": (25, 160), "body_temp": (33, 43), "spo2": (50, 100)}
FALLBACK = {"heart_rate": 72, "systolic_bp": 120, "diastolic_bp": 80, "body_temp": 36.6, "spo2": 97}
STATUS = ["Healthy", "Unhealthy", "Critical"]


def _activity(value):
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        try:
            return float(value) if math.isfinite(float(value)) else 0.0
        except OverflowError:
            return 1e308 if value > 0 else -1e308
    if value == "active":
        return 3.0
    return 0.0


def _scale(value, key):
    if value is None:
        return float("nan")
    low, high = BOUNDS[key]
    return min(1.0, max(0.0, (value - low) / (high - low + 1e-8)))


def _median_lower(values, fallback):
    vals = sorted(float(x) for x in values if math.isfinite(float(x)))
    if not vals:
        return fallback
    return vals[(len(vals) - 1) // 2]


class InferenceEngine:
    def __init__(self):
        self.model = load_model()
        self.prediction_buffers = defaultdict(lambda: deque(maxlen=10))
        self.lock = threading.RLock()
        self.started_at = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.tick = 0
        self.ready = True

    def _vector(self, reading, buffer, exertion=False):
        r = normalized_reading(reading)
        activity = _activity(r.get("activity"))
        if exertion and activity >= 3:
            intensity = 1.0 if r.get("activity") == "active" else 0.7 + (activity - 3) * 0.20
            if r["heart_rate"] is not None:
                r["heart_rate"] = max(25, r["heart_rate"] - 15 * intensity)
            if r["systolic_bp"] is not None:
                r["systolic_bp"] = max(50, r["systolic_bp"] - 15 * intensity)
        base = [_scale(r.get(key), key) for key in VITALS]
        base.append(min(1.0, max(0.0, activity / 5)))
        buffer.append(base)
        medians = []
        for index, key in enumerate(VITALS):
            fallback = (FALLBACK[key] - BOUNDS[key][0]) / (BOUNDS[key][1] - BOUNDS[key][0] + 1e-8)
            medians.append(_median_lower((row[index] for row in buffer), fallback))
        result = [base[i] if math.isfinite(base[i]) else medians[i] for i in range(5)] + [base[5]]
        result.extend([(result[0] - medians[0]) * 4.0, (result[4] - medians[4]) * 5.0])
        return result, r

    def process(self, payload):
        if not valid_payload(payload):
            return False
        valid = [normalized_reading(r) for r in payload["readings"] if valid_reading(r)]
        if not valid:
            return False
        with self.lock:
            self.tick += 1
            tick = self.tick
            tick_time = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            session = self.started_at
            live_buffers = defaultdict(lambda: deque(maxlen=10))
            prepared = []
            for r in valid:
                vec, norm = self._vector(r, live_buffers[r["patient_id"]])
                prepared.append((r, norm, vec))
            x = torch.tensor([item[2] for item in prepared], dtype=torch.float32)
            with torch.inference_mode():
                status_logits, _risk_logits, attention = self.model(x)
                probs = torch.softmax(status_logits, dim=1).cpu().numpy()
                attn = attention.cpu().numpy()
            # Classify every valid reading in sequence, then persist the final row per patient.
            latest = {}
            for i, (raw, norm, _) in enumerate(prepared):
                status_i = int(np.argmax(probs[i]))
                confidence = float(probs[i, status_i])
                if status_i == 2 and confidence < 0.55:
                    status_i = 1
                latest[raw["patient_id"]] = (raw, norm, STATUS[status_i], confidence,
                                                [round(float(v), 4) for v in attn[i]])
            with connect() as conn:
                for pid, (raw, norm, status, confidence, weights) in latest.items():
                    activity = raw.get("activity")
                    if isinstance(activity, float) and not math.isfinite(activity):
                        activity = None
                    conn.execute("""INSERT OR REPLACE INTO ticks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (session, tick, tick_time, pid, status, confidence,
                         *(norm.get(key) for key in VITALS), json_dump(activity), json_dump(weights)))
                # Prediction windows include only rows from this current session and are available from tick 7.
                for pid in latest:
                    rows = conn.execute("SELECT * FROM ticks WHERE session_id=? AND patient_id=? ORDER BY tick DESC LIMIT 7", (session, pid)).fetchall()
                    if len(rows) != 7:
                        continue
                    rows = list(reversed(rows))
                    pred_vectors, risk_meta = [], []
                    for row in rows:
                        raw = {key: row[key] for key in VITALS}
                        raw.update(activity=json.loads(row["activity"]), patient_id=pid)
                        vec, _ = self._vector(raw, self.prediction_buffers[pid], exertion=True)
                        pred_vectors.append(vec)
                        risk_meta.append(row)
                    with torch.inference_mode():
                        _, risk_logits, risk_attention = self.model(torch.tensor(pred_vectors, dtype=torch.float32))
                        risks = torch.sigmoid(risk_logits.reshape(-1)).cpu().numpy()
                        attentions = risk_attention.cpu().numpy()
                    score = round(float(np.mean(risks)), 4)
                    max_i = int(np.argmax(risks))
                    top = [FEATURES[i] for i in np.argsort(-attentions[max_i])[:3]]
                    label = "HIGH RISK" if score >= 0.55 else "LOW RISK"
                    conn.execute("INSERT OR REPLACE INTO predictions VALUES(?,?,?,?,?,?,?)",
                        (session, tick, tick_time, pid, label, score, json_dump(top)))
            return True


_engine = None
_engine_lock = threading.Lock()


def get_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = InferenceEngine()
        return _engine
