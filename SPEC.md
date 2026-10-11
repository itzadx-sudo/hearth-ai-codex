# Hearth AI — Implementation Specification (Stage A, v1.0.1)

**Purpose.** Define a standalone, testable patient-vitals monitoring application for an independent software-development benchmark. Build the application from the contracts below, not from another implementation.

**Rules for builders.** Implement the required behavior, interfaces and security controls. Where the specification is silent, choose an approach and document your reasoning in `DECISIONS.MD`. You may design your own architecture and user interface within the stated stack. Do not seek, inspect or reuse another implementation of this application. Use only these requirements, the supplied model artifact and its fixed inference dependency for application-specific behavior.

**Scope.** Live mode only: simulator → AI server → database → dashboard, plus the device adapter. Replay mode, batch (daily-summary) dashboards, sudden-change detection, context metrics, and model training are out of scope (section 13).

---

## 1. Language and constraints

- **Backend:** Python 3.10+ is required for the AI server, device adapter, simulator, data access and HTTP API. Use Flask for the dashboard/API and SQLite for persistence.
- **Frontend:** HTML and CSS, with vanilla JavaScript permitted for live polling, charts and interaction. Do not use an alternative frontend framework or a different backend language. Bundle frontend assets locally; the application must not depend on external CDNs. A locally vendored standalone JavaScript charting library (for example Chart.js) is permitted; React, Vue, Angular and other frontend application frameworks are not.
- The supplied **PyTorch TabNet checkpoint** and an identical shared inference dependency will be provided (section 11). Do not train, change, or replace the model.
- All persistent state must live under the **required** directory `HEARTH_DATA_DIR`. The application must create this directory when absent.
- **Standard SQLite path:** All required application tables (patients/tick results, predictions, users, assignments and related records) must be stored in **one SQLite database file at `$HEARTH_DATA_DIR/hearth.db`**. Create it automatically on first launch. Do not relocate it through an undocumented setting or split the required tables among databases. The evaluator may verify that this file is present and persists across restarts, but tests of application records and authorization use the defined HTTP/TCP interfaces rather than assuming model-specific table or column names. Internal table names and indexes remain implementation choices, provided the required logical records are stored there. Any additional persistent artifacts must also remain within `HEARTH_DATA_DIR`.
- **Dependencies:** The only permitted direct third-party Python packages are `Flask`, `torch`, `numpy`, `pytest` (self-tests), `requests` (self-tests), `pydantic` (optional validation), `argon2-cffi` or `bcrypt` (optional password hashing). Their required transitive dependencies and the Python standard library are permitted; `hashlib.scrypt` is an acceptable dependency-free password KDF. Declare runtime and development dependencies, with reproducible versions, in `requirements.txt`. The researcher will preinstall requirements in the common environment with `python -m pip install -r requirements.txt`. `start.sh` must **not** install, download or update packages. No external network access is permitted at application runtime. Locally vendored standalone chart assets are allowed as described above.
- The system must run on one machine with no external network services.

## 2. Components, ports and launching

| Component | Interface | Default |
|---|---|---|
| AI server | TCP listener | `127.0.0.1:65432` |
| Device adapter | TCP listener | `127.0.0.1:65431` |
| Dashboard | HTTP server (binds to `127.0.0.1` by default) | port `8050` |
| Simulator | TCP client of the AI server | env `LIVE_N_PATIENTS` (default 50, max 500), `LIVE_TICK_SECONDS` (default 2.0, range 0.5–30) |

**Launch contract.** Provide `./start.sh` that, non-interactively and in the foreground, starts the AI server, the device adapter and the dashboard, and starts the simulator only when `HEARTH_SIMULATE=1`. It must exit cleanly on SIGTERM and stop every child process. Environment: `HEARTH_DATA_DIR` (required), `HEARTH_SESSION_KEY` (cookie-signing secret; random per start if unset), `HEARTH_DASHBOARD_PORT` (default 8050), and the **standard optional admin bootstrap pair** `HEARTH_ADMIN_USER` / `HEARTH_ADMIN_PASS` (section 8.1). When both bootstrap values are provided, `start.sh` must securely create that admin account **before the dashboard becomes ready**, so headless tests can log in. When neither is set, the app may start without an admin; a private local setup command may additionally be offered. Providing only one of the pair must cause startup to fail with a clear **non-secret** error. Never log passwords or commit secrets.

**Simulator environment validation:** `LIVE_N_PATIENTS` defaults to `50`. When present, it must be a **base-10 integer string consisting of ASCII digits `0`–`9` only**, with no sign, spaces, underscores or decimal point, and its numeric value must be **1–500 inclusive** (leading zeros are permitted). `LIVE_TICK_SECONDS` defaults to `2.0`. When present, it must be a **base-10 decimal string** consisting of digits, optionally containing one decimal point with digits on at least one side (valid forms: `2`, `2.`, `2.0`, `0.5`, `.5`; invalid: a lone `.`, `1.2.3`, `2..0`); no sign, spaces, underscores, exponent notation, `NaN` or infinity are permitted. Its parsed value must be finite and **0.5–30 inclusive**. An environment variable explicitly set to the empty string is **invalid**, not absent. Validate both at startup even if `HEARTH_SIMULATE=0`. Do **not clamp** invalid or out-of-range values: print a clear error (without secrets) and exit **nonzero before any listeners are started**. Defaults apply only when variables are absent.

**Other environment validation:** `HEARTH_DASHBOARD_PORT` defaults to `8050`. When present it must be a string of ASCII digits only (no sign, spaces or underscores) whose numeric value is **1–65535** and is neither `65431` nor `65432`. `HEARTH_SESSION_KEY`, when present, must be a non-empty string (no other format is imposed); an empty string is invalid, not absent. Invalid values are handled exactly like invalid simulator variables: a clear non-secret error and a **nonzero exit before any listener starts**.

**Evaluator launch and lifecycle contract:** From the **repository root** (the current working directory), the evaluator preinstalls dependencies with `python -m pip install -r requirements.txt` in a Python 3.10+ environment where the executable `python` is on `PATH`, then runs `./start.sh` with its documented environment variables. All Python subprocesses launched by `start.sh` must use that same `python` environment. `start.sh` must be executable and may not run `pip` or download packages. Within **60 seconds** of launching, all of the following must be true: `GET http://127.0.0.1:<HEARTH_DASHBOARD_PORT>/api/auth_status` returns **HTTP 200** with valid JSON, TCP connections to `127.0.0.1:65432` and `127.0.0.1:65431` succeed, and any configured admin bootstrap has completed. The evaluator starts with `HEARTH_SIMULATE=0` for deterministic API/TCP checks and may separately test `HEARTH_SIMULATE=1`. On SIGTERM sent to the `start.sh` process, it must terminate within **10 seconds**, stop its entire spawned process tree (including a simulator, if enabled), and release all three listener ports. The evaluator verifies process exit and that the ports no longer accept new connections. No background services may survive the launcher. **Immediate port reuse is required:** as soon as the launcher has exited, a new `./start.sh` invocation on the same machine and port numbers must be able to bind `65432`, `65431` and the dashboard port without a manual cooldown, sleep, or OS restart (for example, configure listener socket reuse where needed). Re-launch readiness remains subject to the same 60-second limit.

## 3. Wire protocols

### 3.1 AI server (port 65432)

- **Frame:** 4-byte big-endian unsigned length, then that many bytes of UTF-8 JSON.
- **Payload:** `{"sim_date": "<string>", "readings": [<reading>, ...]}`.
- **Reading:** `patient_id` (int), `timestamp` (`YYYY-MM-DD HH:MM:SS`), `heart_rate`, `systolic_bp`, `diastolic_bp`, `body_temp`, `spo2` (numbers or `null`), `activity` (int 0–5; the string `"active"` is treated as 3 and any other string as 0 for model input).
- **Required handling:**
  - One non-empty frame is one **tick**. The in-memory tick counter initializes to **0**, increments **before storing**, and the **first stored tick is 1** (then 2, 3, ...). Empty/invalid frames do not increment it; one non-empty accepted frame increments it once regardless of patient count. Thus the first eligible prediction is on stored tick **7**, once that patient has seven current-session tick rows.
  - If a frame holds several readings for one patient, **all** readings contribute to sequential preprocessing and are classified, but only the **last** reading/result for that patient is stored for the tick.
  - A declared length above 10 MiB (10,485,760 bytes) closes that connection. The server keeps accepting new connections.
  - Malformed JSON in an otherwise complete frame is skipped; the connection stays open.
  - A payload with no `readings` (missing or empty) is ignored and does not advance the tick counter.
  - A connection that disconnects mid-frame is dropped without affecting other connections or creating a patient.
  - Frames may be split across TCP segments or coalesced; handle both.
  - The server never writes data back to clients.
  - **Payload validation:** A valid frame payload is a JSON object with a nonempty string `sim_date` and a nonempty JSON array `readings`. A different top-level JSON type, non-array `readings`, missing/invalid `sim_date`, or malformed JSON is ignored; no tick is created and the TCP connection stays open. Each array element is considered independently. A **valid reading** must be a JSON object with a `patient_id` that is a **JSON integer token from 1 through 9,223,372,036,854,775,807 (`2^63 - 1`) inclusive** (for example `1`; reject `1.0`, strings, booleans, zero, negative values and larger integers) and a `timestamp` string representing a real local date/time in `YYYY-MM-DD HH:MM:SS` format. Skip readings that fail these structural checks. If **no valid readings** remain, ignore the frame without incrementing the tick, storing data or running inference. If at least one valid reading remains, increment the tick exactly once and process only valid readings in their original order. A bad frame or reading must not crash the server or affect other TCP connections.
  - **Vital-value handling, not physiological validation:** For structurally valid readings, the five vital fields may be omitted or `null`. A valid vital value is a JSON number (integer or decimal) that converts **without overflow to a finite IEEE-754 float64 value**, **not a boolean** (`true` and `false` are invalid even though Python treats `bool` as an `int`). JSON numeric values too large for a finite float64 (for example `1e400` or an extremely large integer) are invalid vitals: treat them as **missing for preprocessing and store/return JSON `null`**, without crashing. Nonstandard JSON numeric tokens such as bare `NaN` or `Infinity` make the **frame malformed** rather than counting as numeric vitals. Missing, `null`, booleans, strings (including `"abc"`), arrays and objects are also **missing and stored/returned as `null`**. Preserve the numeric **value** of finite representable inputs without physiological clamping in storage; float64 normalization/rounding for SQLite storage and API JSON is allowed, and float64 underflow to zero is allowed. Missing/invalid activity maps to **0 for model input**. The activity string `"active"` maps to 3; other activity strings map to 0. **Do not reject readings based only on vital-sign or activity ranges**; scale/clamp numeric features as specified in §5. Activity is stored and returned as received when representable as valid JSON. **Parser digit limits:** the behaviour above is specified for numeric literals of up to 1,000 digits. If a numeric literal is so long that the JSON parser itself refuses it (for example Python's default limit of 4,300 digits for integers), treating the whole frame as malformed is acceptable, as is the reading-level handling above; either way the server must not crash and the connection stays open. An API request body that the parser refuses for the same reason returns 400.

### 3.2 Device adapter (port 65431)

- Accepts **one unframed UTF-8 JSON array** of readings per TCP connection, up to **1,048,576 received bytes (1 MiB)**. Accumulate multiple TCP reads as needed; do not assume the entire array arrives in one segment. **As soon as a complete top-level JSON array with no non-whitespace trailing data already received can be decoded, process it and close the connection without waiting for EOF or a client half-close.** If the client closes first, process only if the buffered bytes form a complete valid array; otherwise discard. An incomplete or malformed array is discarded without forwarding. If the buffer exceeds 1 MiB, drop it and close the connection. Use a **5-second inactivity timeout** for incomplete inputs, then discard and close. Do not send a response body; socket closure indicates completion.
- Renames vendor keys: `vendor_bpm`→`heart_rate`, `vendor_oxygen`→`spo2`, `vendor_movement`→`activity`, `alt_temp`→`body_temp`, `bed_sys`→`systolic_bp`, `bed_dia`→`diastolic_bp`. Other keys pass through unchanged.
- Translate vendor keys first, then apply the **same structural per-reading validity requirements** as the AI server (§3.1). Skip invalid elements and retain valid ones in order. If none remain, close without forwarding or producing a tick.
- Forwards the surviving readings as **one framed payload** (section 3.1) to the AI server with `sim_date` set to today (`YYYY-MM-DD`). One adapter connection therefore produces at most one tick.
- If the AI server connection fails, retry once; then log and drop the batch. Malformed, oversized, incomplete, or timed-out JSON is logged and ignored. The adapter must continue accepting new connections after any of these failures.
- `start.sh` must start the adapter.

## 4. Constants

| Name | Value |
|---|---|
| Classes (index order) | 0 Healthy, 1 Unhealthy, 2 Critical |
| Feature order (8) | heart_rate, systolic_bp, diastolic_bp, body_temp, spo2, activity, delta_hr, delta_spo2 |
| Normalisation bounds (min, max) | heart_rate 20–220; systolic_bp 50–280; diastolic_bp 25–160; body_temp 33–43; spo2 50–100 |
| Fallback medians (five vitals only) | heart_rate 72; systolic_bp 120; diastolic_bp 80; body_temp 36.6; spo2 97. Missing/invalid activity maps to 0 and is not imputed. |
| Low-confidence threshold | 0.55 |
| Risk label threshold | 0.55 |
| Prediction window | 7 ticks |
| First prediction tick | tick ≥ 7 |
| Imputation buffer depth | 10 readings per patient |
| Exertion bias (HR, SBP) | 15, 15 (applied only when activity ≥ 3; see 6) |
| Max alert list size | 200 |

## 5. Per-tick classification (AI server)

For each patient's evaluated reading:

1. **Scale.** Each vital → `clip((v − min) / (max − min + 1e-8), 0, 1)`. Activity → `clip(activity / 5, 0, 1)`. Missing, nonnumeric, boolean or nonfinite vitals are "missing". Missing/invalid activity is **0** for model input; activity is **never imputed**.
2. **Sequential imputation (live classification).** At the start of **each incoming frame**, create a fresh, empty circular buffer **for each patient** (capacity 10 base-feature vectors). For that patient, process readings **in the order they arrive** in the frame. For each reading:
   - Convert the five vitals and activity to the six scaled base features from step 1. Represent missing vitals as NaN; convert missing/invalid activity to 0 for model input.
   - **Push the current six-feature vector into the patient's buffer first**, overwriting the oldest entry when full. The buffer therefore contains the current reading and up to nine previous readings **from this frame only**.
   - Compute a separate, per-feature **NaN-ignoring median** across the buffer **after that push**. For an even number of valid values, use the **lower middle value**. For a **vital** with no valid value, use its scaled fallback median from §4. **Never impute activity:** its converted value (including 0 for missing/invalid) passes straight through, regardless of the buffer median.
   - Replace **missing vitals only** in the current reading with these medians; retain present vitals and the activity value unchanged. **Do not** feed imputed values back into the buffer; the buffer stores the original scaled inputs, including missing vitals as NaNs.
   - The live classification buffer is **discarded after the frame**; it does not carry over between incoming frames.
3. **Deltas.** Using the **imputed current HR/SpO2** and the **post-push medians** from step 2, calculate `delta_hr = (hr_imputed_scaled − median_hr_scaled) × 200/50` and `delta_spo2 = (spo2_imputed_scaled − median_spo2_scaled) × 50/10`. With one complete reading per patient in a frame, both deltas are 0. Append these to form the model's eight input features.
4. **Infer.** Run the provided model on the 8-feature vector. Status = argmax of softmax over the 3 status logits; confidence = that probability.
5. **Downgrade.** If status is Critical and confidence < 0.55, status becomes **Unhealthy** (confidence unchanged). This is the stored value.
6. **Attention.** Store the model's 8 per-feature attention values (rounded to 4 decimals) with the tick result.
7. **No exertion adjustment** is applied before classification.
8. **Store** one tick result per patient (section 7).

## 6. Seven-tick risk prediction

- Runs after storing tick results when the tick counter is ≥ 7.
- For each patient in the current frame whose last **7 stored tick rows** exist (oldest first): apply the exertion adjustment, then scale, impute and derive deltas using the **same post-push sequential algorithm** from section 5, but with a **separate persistent per-patient prediction buffer** (capacity 10). Process all seven rows in order on **every prediction call**, pushing all seven even if some were processed in earlier overlapping prediction windows. Do **not** reset the prediction buffer between calls. It stores scaled (possibly missing) input features, not imputed values. The resulting deltas are relative to the rolling medians after each push and can therefore vary across calls. Outputs must follow the defined model and preprocessing contract.
  - Exertion adjustment: if activity ≥ 3, `intensity = 0.7 + (activity − 3) × 0.20`; `heart_rate = max(25, hr − 15 × intensity)`; `systolic_bp = max(50, sbp − 15 × intensity)`. For the string `"active"`, intensity is 1.0.
- Model risk output per row → sigmoid. `risk_score` = mean over the 7 rows, rounded to 4 decimals. `risk_label` = `HIGH RISK` if `risk_score ≥ 0.55`, else `LOW RISK`.
- `top_factors` = the 3 feature names with the highest attention on the row with the highest risk probability, highest first.
- Store one prediction per patient per tick; the API serves the latest per patient.
- Patients with fewer than 7 stored tick rows in the **current session** have no prediction. **A tick is an accepted frame containing at least one structurally valid patient reading, not a day. This is a seven-tick rolling risk estimate, not a seven-day clinical forecast.**
- Interpret activity on its original, unscaled numeric scale before evaluating exertion. The string "active" maps to activity level 3 but uses intensity 1.0. Missing, invalid, boolean or other nonnumeric activity values map to 0. For finite numeric activity values of at least 3, use the specified intensity formula.

- Apply exertion adjustments independently to heart rate and systolic blood pressure. If either vital is missing or invalid, leave that field missing for subsequent imputation. Only scale activity by dividing by 5 when preparing the model input.

## 7. Storage (logical)

SQLite is required. Store all the following records in `$HEARTH_DATA_DIR/hearth.db` (sections 1 and 7). Required content:

- **Tick results:** session id, tick, tick time (`YYYY-MM-DD HH:MM:SS`, server clock), patient id, status, confidence, the 5 vitals **as finite numbers or `null` after §3.1 validation** (invalid/missing vitals become `null`), and activity **as received**, attention as a JSON object.
- **Predictions:** session id, tick, time, patient id, risk label, risk score, top factors (JSON list).
- **Users:** username (unique), **salted password hash using a password-specific KDF** (e.g. Argon2id, scrypt, or bcrypt), role (`guardian` default, or securely provisioned `admin`), optional display name. Never store plaintext or unsalted SHA-256 passwords.
- **Guardian–patient assignments:** (username, patient id), unique pair.
- **Database location:** all these required records reside in `$HEARTH_DATA_DIR/hearth.db` as defined in section 1, with durable SQLite transactions and schema initialization at startup.
- **Session id** = server start time `YYYYMMDD_HHMMSS`. The in-memory counter initializes to 0 on every server start; the **first stored tick is 1**. The "current session" is the session of the most recently stored tick row. The evaluation runner must avoid two server starts within the same timestamp second. **After a restart with no newly accepted frames, the most recently stored session remains current and its persisted data stays visible.** Once a new server session stores its first tick, that session becomes current. If no tick has ever been stored, there is no current session.
- Users, assignments and live data must survive a restart.

## 8. REST API (dashboard server)

JSON everywhere except `/` and `/landing`. Cookie-based session. Unknown fields may be added; listed fields must exist.

**Session scope:** Unless an endpoint explicitly says otherwise, all live patient lists, patient detail/history, live summaries, tick series, statistics, and current predictions refer only to the **most recently persisted session with at least one stored tick**, including after a process restart before any new frames have arrived. Authorization filtering is applied within that session. **Exception:** `/api/alerts` intentionally searches all retained sessions (§8.2), subject to the same guardian assignments. A guardian with no visible ticks receives the empty views described below and must not learn another session's identifier.

### 8.1 Auth

| Endpoint | Behaviour |
|---|---|
| `POST /api/signup` `{username, password, role?}` | Public signup creates **guardians only**. Missing username or password → 400 `{"error":"Missing credentials"}`. Created → 200 `{"message":"User created"}`. Duplicate → 400 `{"error":...}`. Reject any request for `admin` or an unsupported role with 403. `role` defaults to `guardian`. |
| `POST /api/login` | OK → 200 `{"message":"Logged in","user":{username,role,display_name}}`. Otherwise 401 `{"error":"Invalid credentials"}`. |
| `POST /api/logout` | Clears the session; `{"message":"Logged out"}`. `GET /api/logout` must return 405 without changing the session. |
| `GET /api/auth_status` | `{"logged_in":false}` or `{"logged_in":true,username,display_name,role,patients}` (`patients` = assigned ids for guardians, `[]` otherwise). |
| `POST /api/update_name` `{display_name}` | Logged in with valid input → 200; unauthenticated → 401; invalid display name → 400. A valid name is a JSON string, trimmed of surrounding whitespace, 1–80 Unicode code points after trimming, and contains no control characters (U+0000–U+001F or U+007F). Store the trimmed value. |
| `POST /api/assign_patient` `{guardian_username, patient_id}` | Unauthenticated → 401; authenticated non-admin → 403 `{"error":"Unauthorized"}`. `patient_id` must be a JSON integer token from **1 through 9,223,372,036,854,775,807 (`2^63-1`) inclusive** (so `1.0`, booleans, zero, negative and larger IDs are invalid); invalid values → 400. Unknown or non-guardian user → 400. Assignments to valid positive patient IDs **are allowed before sensor data exists** for that patient. Valid request → 200; repeated assignment is idempotent. |
| `GET /api/guardians` | Non-admin → 403. Otherwise a list of guardian usernames. |

**Mandatory security requirements:**

- **Authentication:** Public signup creates guardians only; admin access must **not** be granted via `role: "admin"` or a hardcoded demo password. **Headless bootstrap contract:** when `HEARTH_ADMIN_USER` and `HEARTH_ADMIN_PASS` are both nonempty at startup, create that username as an `admin` if it does not already exist, hashing the supplied password with the required password KDF. The same bootstrap values may be provided on later restarts: an existing admin is left unchanged (including its password), not duplicated. If that username already belongs to a guardian, **fail rather than silently promote** it. Reject empty values, partially provided pairs and conflicting accounts with a clear error that does not reveal secrets. If both variables are absent, no automatic admin is created. A private local CLI setup tool is optional, but **does not replace** the environment-variable contract.
- **Access:** Unauthenticated users may reach `/landing`, `/api/signup`, `/api/login`, `/api/auth_status`, and `POST /api/logout`; `GET /` must return **HTTP 302** with `Location: /landing` until login. Unauthenticated requests to **all patient, live, overview, alert, system, assignment and other protected API endpoints** return HTTP **401** without disclosing patient data. Authenticated guardians can view **only their assigned patients**. Authenticated admins can view all patients. Deny unassigned patient access with **403**; filter aggregate counts, leaderboards, live statistics, predictions and alert feeds so they cannot reveal unassigned patients. Protect every supported patient-scoped endpoint consistently.
- **Privileges:** Only admins may assign patients, list guardians, or invoke/view training controls. Authenticated non-admin callers receive **403** for those endpoints; unauthenticated callers receive **401**.
- **Passwords / sessions:** Use a per-user salt and password-specific KDF; do not store unsalted SHA-256 hashes or plaintext passwords. Protect session cookies with `HttpOnly`, **`SameSite=Strict`**, and `Secure` under HTTPS; use a strong secret and do not expose secrets in logs.
- **Standard CSRF contract (no token):** For **every POST API request**, including signup, login, logout, update-name, patient assignment and retrain, require exactly one `Origin` header matching **`http://127.0.0.1:<HEARTH_DASHBOARD_PORT>`** (default `http://127.0.0.1:8050`) by scheme, host and port. When HTTPS is deliberately configured, match the correspondingly configured HTTPS origin instead. Reject an absent, `null`, malformed, duplicate or nonmatching `Origin` with **HTTP 403** and `{"error":"Invalid origin"}` **before authentication, authorization, payload validation, or state changes**. Origin validation is the first application-level check on every POST API request; thus even an unauthenticated POST or malformed payload with an invalid Origin returns 403. All API POST requests from the dashboard and the headless evaluator must include that header; no CSRF-token endpoint or header is required. Do not offer cross-origin credentialed API access. Keep `GET` requests read-only; logout is POST-only as specified above. Use **`http://127.0.0.1:<port>`**, not `http://localhost:<port>`, in the browser, documentation and tests; `localhost` Origins are deliberately not accepted by this contract.
- **System endpoint:** `GET /api/system` is **admin-only**. Unauthenticated requests return 401; an authenticated guardian receives 403 with `{"error":"Unauthorized"}`. Guardians' `/api/overview` must include `system_health: {}` rather than global system statistics; admins receive the full `system_health` object described for the endpoint. The System UI must not display or request admin-only information for guardians.
- **Guardian-scoped aggregate contract:** All patient-data responses, including `/api/patients`, individual patient views, `/api/live`, `/api/overview`, leaderboards, alerts and histories, must operate on **the assigned patient IDs only** for guardians. On the current session, a **visible tick** is a tick with at least one stored row for an assigned patient. For guardians: `summary.total_ticks` = count of distinct visible ticks; `summary.total_patients` = distinct assigned patients with a current-session tick result; `summary.status_counts` = counts of tick rows by status **across visible ticks for assigned patients**; `summary.high_risk_patients` = number of assigned patients whose latest current-session risk score is ≥ 0.5. `tick_series` = the latest 40 visible ticks (chronological), with each status count using assigned-patient rows only; `tick_stats` = the most recent visible tick, computed entirely from assigned-patient rows (same numeric fields as §8.2). Preserve the global stored tick IDs in visible tick entries; their sequence may contain gaps. `overview.summary`, `overview.tick_stats`, `overview.day_summary`, `overview.patients`, `overview.leaderboard`, `overview.recent_alerts` and `/api/live.predictions` must use the same patient filter. If a guardian has no visible ticks, `/api/live` and `/api/overview` return **the exact empty response contracts** defined in §8.2 with `session_id: null`, even when other patients have live ticks. Do not reveal the existence or identifier of a session containing only other patients. Admins receive all recorded patient data. Alerts may span all sessions but still require assignment filtering.
- **Local exposure:** The dashboard binds `127.0.0.1` by default; it does not require public internet or external services. Document any optional network binding separately. Use **synthetic patient data only**.

Apply these safeguards to every applicable endpoint.

### 8.2 Data endpoints (live mode)

- **`GET /api/patients`** — `[]` before any ticks exist; otherwise a list sorted by `risk_score` descending. Each entry: `patient_id`, `session_id`, `tick`, `tick_time`, `status`, `confidence`, `heart_rate`, `systolic_bp`, `diastolic_bp`, `body_temp`, `spo2`, `activity`, `attention_weights` (JSON string), `risk_score` (0.0 if no prediction), `risk_label` (`"—"` if no prediction), plus aliases `worst_status` (= status), `sim_date` (= tick_time), `avg_heart_rate`, `avg_systolic`, `avg_diastolic`, `avg_temp`, `avg_spo2` (= the vitals).
- **`GET /api/patients/<pid>`** — unauthenticated → 401; unassigned guardian → 403 `{}`. Otherwise `{patient_id, current_status{worst_status, sim_date, avg_heart_rate, avg_systolic, avg_diastolic, avg_temp, avg_spo2, confidence}, latest_prediction, context_metrics: {}, vitals_trend{dates, heart_rate, systolic_bp, body_temp, spo2}, history}` where `history` is the last 20 tick rows, oldest first.
- **`GET /api/patient/<pid>`** — unauthenticated → 401; unassigned guardian → 403 `{"error":...,"found":false}`; no session → 404; unknown patient → 404 `{"error":...,"found":false}`. Otherwise `{"found":true, session_id, patient}` where `patient` is the latest tick row plus `attention` (object or null), `history` (all ticks, oldest first: tick, tick_time, status, confidence, vitals, activity) and `prediction` (latest prediction row with `top_factors` as a list, or null).
- **`GET /api/live`** — no persisted session **or no ticks visible to the guardian** → `{"session_id":null,"summary":{},"predictions":[],"tick_series":[],"tick_stats":{},"message":"No live session found. Waiting for data..."}`. Otherwise:
  - `summary`: `{session_id, total_ticks, total_patients, status_counts (counts of tick rows by status), high_risk_patients (patients whose latest prediction has risk_score ≥ 0.5)}`.
  - `predictions`: latest per patient, sorted by `risk_score` descending, up to 200, each with `computed_at_tick`, `computed_at_time`, `patient_id`, `risk_label`, `risk_score`, `top_factors` (JSON string).
  - `tick_series`: the last 40 ticks, oldest first, each `{tick, tick_time, Healthy, Unhealthy, Critical}` (patient counts).
  - `tick_stats`: for the latest tick `{tick, patient_count, status_counts, avg_heart_rate, avg_systolic, avg_diastolic, avg_temp, avg_spo2}` (averages rounded to 2 decimals, nulls ignored).
- **`GET /api/overview`** — `{live_mode: true, session_id, patients (latest tick row per patient), tick_stats, day_summary (= tick_stats), leaderboard (top 10 latest predictions by risk_score), recent_alerts (at most 12), system_health, summary}`. In `recent_alerts`, critical entries are patients whose **latest** status is Critical; predictive entries are latest predictions with `risk_score ≥ 0.5`. **When no session has stored ticks, or when a guardian has no visible ticks**, return the exact patient-data shape `{"live_mode":true,"session_id":null,"patients":[],"tick_stats":{},"day_summary":{},"leaderboard":[],"recent_alerts":[],"summary":{},"system_health":{}}` **for guardians**. For **admins**, use the same empty patient-data fields but populate `system_health` with the authorized `GET /api/system` response (§8.2). The `live_mode` flag remains `true` because Stage A is a live-mode application.
- **`GET /api/alerts`** — filter by the caller's assigned-patient visibility **before selecting and capping** alert candidates; sort by `timestamp` descending, then cap at 200. Entry: `id` (null), `patient_id`, `alert_type` and `type` (both `critical` or `predictive`), `timestamp` and `sim_date` (same value), `confidence`, `risk_label`, `top_factors` (list). **No debounce:**
  - one `critical` entry for each patient with at least one stored Critical tick (most recent such tick; `confidence` = that tick's confidence; `risk_label` null; `top_factors` `[]`), limited to the **100 most recent visible critical patients, after visibility filtering**;
  - one `predictive` entry for each patient with at least one stored HIGH RISK prediction (`confidence` = `risk_score`; `risk_label` = `HIGH RISK`).
  - Both look across **all retained sessions**, not just the current one, and entries persist across session changes. Apply visibility filtering before all per-type or total limits.
- **`GET /api/system`** — **admin-only** (unauthenticated → 401; guardian → 403). Response for admins: `{total_patients, days_processed, model_status ("loaded" or "missing"), predictor_status (same), db_size_mb, live_ticks, live_session ("—" if none), live_size_mb}`. `total_patients` and `days_processed` are 0 in live-only builds. `model_status` and `predictor_status` are `"loaded"` only when the supplied inference dependency successfully loads the checkpoint and is ready to execute inference; otherwise both are `"missing"` (file existence alone is insufficient). Since the experiment uses a **single** SQLite database, both `db_size_mb` and `live_size_mb` are **the same measured main-file size**: `round(os.path.getsize("$HEARTH_DATA_DIR/hearth.db") / 1048576, 2)` in MiB (excluding WAL/SHM sidecar files). If the database does not yet exist, both are `0.0`. `live_ticks` is the number of stored ticks in the current session, or 0 if none.
- **`POST /api/retrain`** and **`GET /api/training_status`** are admin-only (unauthenticated → 401; signed-in non-admin → 403). `GET /api/training_status` returns `{"training": bool, "message": str}` for admins. Stage A requires endpoints and authorization; actual training is out of scope (it may return an error).
- **`GET /`** serves the dashboard to authenticated users and returns **302** to `/landing` for unauthenticated users; **`GET /landing`** serves a landing page with sign-up and login. All POST requests from the frontend must attach the standard same-origin `Origin` header (browsers send it for same-origin fetch POST; test clients must explicitly set it).

## 9. Dashboard (functional requirements)

A single-page web UI driven by the endpoints above, auto-refreshing every few seconds. Required UI views:

- **Overview** — status counts for the latest tick, top-10 risk leaderboard, recent alerts, system health.
- **Patients** — table of all visible patients sorted by risk: status, confidence, risk label and score, current vitals. Selecting a patient opens a drill-down with vitals trend charts, latest prediction with top factors, and the attention weights that drove the classification.
- **Live Monitor** — status counts over the last 40 ticks (chart) and latest predictions.
- **Alerts** — combined critical and predictive alert feed.
- **System** — admin-only system statistics from `/api/system` and admin-only retrain control. Guardians must not receive global system fields; their Overview can use an empty `system_health` object.
- **Account** — login, logout, sign-up, display name; admins can assign patients to guardians.

Visual styling is free. Behaviour must be usable with up to 500 patients.

## 10. Simulator

- Connects to the AI server and, every `LIVE_TICK_SECONDS`, sends one frame with one reading for each of `LIVE_N_PATIENTS` patients (ids 1..N).
- Readings follow per-patient profiles: mostly healthy, sometimes unhealthy, occasionally a critical episode lasting about 2–4 consecutive ticks, plus random sensor dropouts (null vitals). The exact distribution is **not pinned**, but over several minutes with 50 patients the run should produce all three statuses.
- Reconnects automatically if the server connection drops.
- Timestamps use the local clock, `YYYY-MM-DD HH:MM:SS`.

## 11. Model contract

- The researcher must provide the **identical immutable `shared_model/` directory at the repository root**, containing the unchanged **`shared_model/hearth_tabnet.pth`** checkpoint and only the neural-network architecture/loading/inference wrapper. It must contain **no** application preprocessing, data storage, server, simulator or UI code. Builders may import this package but **must not edit it**. Model training, weight modification and conversion are out of scope.
- **Fixed import and call contract to be implemented in the supplied dependency:** `from shared_model import load_model`; `model = load_model()` returns a ready-to-infer PyTorch module on CPU in evaluation mode; `status_logits, risk_logits, attention = model(x)` for a `torch.float32` CPU tensor `x` of shape `[N, 8]` (already scaled, imputed and provided with deltas according to §§4–6). Output shapes are `[N, 3]`, `[N, 1]`, `[N, 8]` respectively, with attention rows summing to approximately 1. `N=1` must work. The researcher can support optional accelerator use without altering this required CPU interface. The shared package must be **self-contained**, including every neural-network architecture class required to deserialize/load its checkpoint, with no imports from other application source files. The `load_model()` wrapper must **always expose all three outputs on every call**, including attention; it may handle model-internal flags privately. The researcher must test CPU evaluation mode and batch sizes **1 and greater than 1** before distributing the package.
- **Prerequisite, not a delivered artifact in this documentation release:** The researcher must **build and verify** this wrapper and checkpoint package on the common runner **before any builder starts**. The evaluator preserves an untouched original, checks the folder's published hash before each independent run, and restores it from that pristine copy if modified. The same preverified package and import path must be supplied to all builders. Until it exists and its outputs have been verified, the benchmark is **not ready to run**. The builders own preprocessing, serving, persistence and UI; they do not own neural-network architecture or training.

## 12. Additional consistency requirements

- Alerts have no debounce and never clear once raised (section 8.2).
- `high_risk_patients` and overview predictive alerts use `risk_score ≥ 0.5` while the label uses `≥ 0.55`.
- Overview critical alerts follow the latest status; `/api/alerts` follows any stored Critical tick (all sessions).
- Exertion adjustment applies to risk prediction but not to live classification.
- `activity` is stored and returned exactly as received (even a string).

## 13. Out of scope and security requirements

**Out of scope (not required, not scored):** replay mode, batch/daily-summary views, sudden-change detection, context-metric endpoints and model training. The live **simulator** in section 10 remains required.

**Security and data-use requirements:** Enforce guardian-only public signup, authentication for patient data, role-aware assignments and aggregate filtering, salted password-specific hashing, localhost binding and Origin-based CSRF checks (section 8.1). These requirements are mandatory. Use **synthetic patient data only**.

**Performance.** No fixed latency target is given. Performance will be measured under the same load for every build (for example a 500-reading frame every 2 seconds); keep per-tick processing well inside the tick interval.

---

## 14. Builder process rules

- **Deliverables:** a git repository containing the implementation, `start.sh` (section 2), and a `README.md` with design notes, any deviations from this document, and the weaknesses you observed.
- **Sources:** Use this specification, the supplied checkpoint and the fixed shared inference dependency for application-specific requirements. Do not visit, search for, browse, clone, or reuse any existing Hearth AI application source, mirror or related implementation. Official programming and dependency documentation may be consulted for generic technical reference. Do not modify the shared dependency.
- **Independent development and agents:** each implementation may have **at most three simultaneously active coding agent instances (the primary included)**. This is a **concurrency cap, not a lifetime total**: a finished/terminated instance may be replaced by a new instance, but every instance and invocation must be logged. **The primary, every subagent, any coding reviewer and every fallback must use the exact same assigned model ID and version throughout the build**. Sharing a model *family* is insufficient: no stronger tier, different release/version, auto-routed fallback, external expert model or competing implementation may be used. If a tool cannot guarantee the assigned model/version for a call, do not make that call; report the limitation. Agents may implement, debug, review and coordinate locally, but the result is one submission. Log each instance, exact model/version, role, start/end or handoff, peak concurrency and any available input/output token usage in `DECISIONS.MD`. The operator independently checks model routing, agent concurrency and all primary/subagent/reviewer token consumption using the available platform/tool logs (unavailable measurements are marked unknown, never zero). No human implementation/debugging assistance is allowed. Use the same researcher-provided materials and any operator-provided public tests as every other builder; additionally write your own self-check tests under `tests/public/` and run them using `python -m pytest tests/public`. Builder-written self-checks do **not** replace the independent evaluation. Record actual commands, results, meaningful failures, fixes and unresolved blockers in `DECISIONS.MD` and `README.md`.
- **Finishing:** when you believe the work meets this document and runs from a clean checkout, commit your implementation and documentation, record the final commit SHA in `README.md`, and reply with the single word `DONE` on its own line. The researcher will preserve that commit and run **one final independent evaluation**. Do not modify the submitted implementation afterward.
- **Human involvement:** the human operator may supply the common materials, start sessions, collect usage logs and run the same evaluation for each build. They must not write or debug application code, provide implementation solutions or offer one model extra technical guidance. If the specification is silent, make a reasonable choice and record the assumption in `DECISIONS.MD`. If you cannot complete the work, document the blocker and submit the incomplete state honestly.
