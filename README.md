# Hearth AI — Live Monitoring Demo

This repository contains a local synthetic-patient monitoring demo. A simulator or device adapter sends readings to a TCP inference service; the service classifies each accepted tick with the supplied fixed model, stores results in SQLite, and serves a dashboard and JSON API. This is not a clinically validated system or medical device.

## Requirements and launch

Use Python 3.10 or newer. Runtime and self-test dependencies are pinned in `requirements.txt` and may be installed before launch:

```bash
python -m pip install -r requirements.txt
```

`start.sh` does not install dependencies. Set the required data directory and, for headless login, both admin bootstrap values. The password below is a prompt value and should not be placed in shell history or committed:

```bash
export HEARTH_DATA_DIR="$PWD/.hearth-data"
export HEARTH_ADMIN_USER=admin
read -s HEARTH_ADMIN_PASS
export HEARTH_ADMIN_PASS
export HEARTH_SIMULATE=1
./start.sh
```

Set `HEARTH_SIMULATE=0` for deterministic manual/API runs. The simulator defaults to 50 patients at 2 seconds per tick; optional `LIVE_N_PATIENTS` accepts ASCII integer strings from 1 through 500 and `LIVE_TICK_SECONDS` accepts unsigned base-10 decimal values from 0.5 through 30. Both are validated even when simulation is disabled. `HEARTH_DASHBOARD_PORT` defaults to 8050; `HEARTH_SESSION_KEY` is generated randomly when absent and must not be empty when provided. The optional `HEARTH_ADMIN_USER` and `HEARTH_ADMIN_PASS` must be set together. Bootstrap is idempotent and will not promote a guardian account. No secret is written to this README or application logs.

The database is created at `$HEARTH_DATA_DIR/hearth.db`. The three listeners bind to loopback: dashboard `http://127.0.0.1:<port>`, AI TCP port 65432, and adapter TCP port 65431. Open the dashboard using the numeric loopback address `127.0.0.1`. Stop all services with Ctrl-C or SIGTERM to `start.sh`.

## Application behavior

- AI input uses a four-byte big-endian length followed by UTF-8 JSON. Invalid frames/readings do not create ticks; patient IDs are validated as positive JSON integers no larger than `2^63-1`; invalid and float64-overflow vital values are persisted and returned as `null`.
- The device adapter accepts segmented JSON arrays up to 1 MiB, validates and renames vendor fields, then forwards one framed batch. Incomplete inputs time out after five seconds.
- Live classification uses per-frame, per-patient sequential median imputation. Seven-tick risk windows use the fixed model and a separate persistent in-process prediction buffer. Tick results, predictions, users, and assignments use the same SQLite database.
- The dashboard provides overview, patient table and detail, live status trends, alerts, account controls, and admin-only system and assignment views. Frontend assets are local and use vanilla JavaScript.
- Public signup only creates guardians. Passwords use salted scrypt hashes. Every API POST requires the exact loopback `Origin`; session cookies are HttpOnly and SameSite Strict. Admin-only controls and guardian assignment filters apply to patient rows, histories, summaries, alerts, and leaderboards.
- All demo readings are generated synthetic values. Training, replay, daily summary, and clinical decision support are outside this Stage A application.

## Self-checks and verification

From the repository root, run the required public self-check suite:

```bash
python -m pytest tests/public
```

The checks cover strict IDs and vital normalization, nonadvancing invalid frames, activity defaults, the shared model batch interface, segmented near-limit adapter payloads, seven-tick predictions, Origin and role checks, guardian filtering, exact empty responses, invalid environment formats, readiness, admin bootstrap, persisted-session visibility after restart, shutdown, and immediate port reuse.

**Actual local result (2026-10-11):** `PATH=/private/tmp/hearth-python-bin:$PATH python -m pytest tests/public` — **9 passed, 0 failed, 0 skipped** in 6.14 seconds using Python 3.12.9 and pytest 9.1.1. The temporary `python` alias points to the installed `python3`; the workspace itself does not expose a `python` executable. Python compile checks and Node syntax checks for both browser scripts also passed.

## Design notes and limitations

The service launcher validates configuration before starting children, provisions an admin before the dashboard becomes ready, forwards termination, and waits for every service process. TCP sockets enable address reuse. The AI inference package remains unchanged and is loaded through its documented `load_model()` interface. Its checkpoint SHA-256 is `9960f898d775cc7b984e530238f09ce0487a62684ba574475c8094fda1d18728`.

The dashboard serves plain HTTP on loopback, so the session cookie's Secure flag is disabled for this local-only configuration. The default signing secret is random per launch; operators who need sessions to survive a restart should set a strong `HEARTH_SESSION_KEY` outside the repository. The database uses SQLite WAL mode; reported database size measures the main `hearth.db` file as specified and excludes WAL/SHM sidecars. Risk values are model outputs over synthetic data and must not guide care.

Decisions, assumptions, fixes, and verification evidence are tracked in `DECISIONS.MD`. `RULES.md`, `SPEC.md`, `SCORE_TEMPLATE.md`, and all files in `shared_model/` are supplied benchmark materials and remain unchanged.

## Builder record

| Item | Value |
|---|---|
| Model / exact assigned version | GPT-6 family; exact runtime ID/version unavailable in exposed metadata |
| Agent instances | One primary instance; no delegates or reviewers; peak concurrency 1 |
| Token usage | Unknown; platform metrics unavailable |
| Branch | `main` |
| Python used locally | Python 3.12.9 (`python3`) |
| Shared checkpoint SHA-256 | `9960f898d775cc7b984e530238f09ce0487a62684ba574475c8094fda1d18728` |
| Public self-test command | `python -m pytest tests/public` |
| Actual self-test result | 2026-10-11: 9 passed, 0 failed, 0 skipped; 6.14 seconds |
| Known limitations | Synthetic demo only; no training/replay/daily summaries; local HTTP only; long-run status mix and browser accessibility not measured |
| Verified implementation commit SHA | `ac569a1bb9eb7d28443a86b169e66345431bdc21` |
| Final commit SHA | The documentation-only finalization commit is reported in the completion response |
