import math
import os
import re
import sys


def _env_value(name, default):
    return os.environ[name] if name in os.environ else default


def validate_environment():
    n_raw = _env_value("LIVE_N_PATIENTS", "50")
    tick_raw = _env_value("LIVE_TICK_SECONDS", "2.0")
    port_raw = _env_value("HEARTH_DASHBOARD_PORT", "8050")
    session_key = _env_value("HEARTH_SESSION_KEY", None)
    simulate = _env_value("HEARTH_SIMULATE", "0")
    errors = []
    if not re.fullmatch(r"[0-9]+", n_raw, flags=re.ASCII):
        errors.append("LIVE_N_PATIENTS must contain ASCII digits only")
    else:
        try:
            if not 1 <= int(n_raw) <= 500:
                errors.append("LIVE_N_PATIENTS must be between 1 and 500")
        except ValueError:
            errors.append("LIVE_N_PATIENTS is too long to be a supported integer")
    if not re.fullmatch(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", tick_raw, flags=re.ASCII):
        errors.append("LIVE_TICK_SECONDS must be a base-10 decimal without sign or exponent")
    else:
        value = float(tick_raw)
        if not math.isfinite(value) or not 0.5 <= value <= 30:
            errors.append("LIVE_TICK_SECONDS must be between 0.5 and 30")
    if not re.fullmatch(r"[0-9]+", port_raw, flags=re.ASCII):
        errors.append("HEARTH_DASHBOARD_PORT must contain ASCII digits only")
    else:
        try:
            port_value = int(port_raw)
            if not 1 <= port_value <= 65535 or port_value in (65431, 65432):
                errors.append("HEARTH_DASHBOARD_PORT must be 1-65535 and differ from 65431/65432")
        except ValueError:
            errors.append("HEARTH_DASHBOARD_PORT is too long to be a supported integer")
    if session_key == "":
        errors.append("HEARTH_SESSION_KEY must not be empty")
    if simulate not in ("0", "1"):
        errors.append("HEARTH_SIMULATE must be 0 or 1")
    data_dir = os.environ.get("HEARTH_DATA_DIR")
    if not data_dir:
        errors.append("HEARTH_DATA_DIR is required and must not be empty")
    admin_user = os.environ.get("HEARTH_ADMIN_USER")
    admin_pass = os.environ.get("HEARTH_ADMIN_PASS")
    if (admin_user is None) != (admin_pass is None):
        errors.append("HEARTH_ADMIN_USER and HEARTH_ADMIN_PASS must be provided together")
    if admin_user is not None and (not admin_user or not admin_pass):
        errors.append("Admin bootstrap values must be non-empty")
    if errors:
        for error in errors:
            print(f"Configuration error: {error}", file=sys.stderr)
        raise SystemExit(2)
    os.environ["HEARTH_DASHBOARD_PORT"] = str(int(port_raw))
    os.environ["LIVE_N_PATIENTS"] = str(int(n_raw))
    os.environ["LIVE_TICK_SECONDS"] = str(float(tick_raw))
    return {
        "data_dir": data_dir,
        "port": int(port_raw),
        "session_key": session_key,
        "simulate": simulate == "1",
        "admin_user": admin_user,
        "admin_pass": admin_pass,
    }


def db_path():
    return os.path.join(os.environ["HEARTH_DATA_DIR"], "hearth.db")
