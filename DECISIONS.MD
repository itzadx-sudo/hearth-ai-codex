# DECISIONS — Engineering Decision Log

## D-001 — Single-process coordinator with independent service listeners
- **When / milestone:** 2026-10-11T06:51:08Z / initial inspection
- **Status:** Adopted
- **Requirement:** `SPEC.md` §§2–3, 7–8
- **Decision:** Use one Python package for shared SQLite/model/preprocessing logic, with AI TCP, adapter TCP, and Flask dashboard launched as managed child processes by `start.sh`.
- **Why:** Clear service boundaries keep each public protocol testable while a single durable database and inference implementation prevent divergent behavior.
- **Alternatives considered:** One monolithic process; three unrelated service implementations. Both make lifecycle or shared state harder to reason about.
- **Trade-offs / risks:** Process supervision and signal cleanup need explicit handling; SQLite serializes writes.
- **Implementation:** `hearth/launch.py`, `database.py`, `engine.py`, `tcp_services.py`, and `web.py`; managed subprocess lifecycle in `start.sh`.
- **Verification:** Initial environment check found no `python` executable, but `python3` is Python 3.12.9. Supplied model CPU evaluation inference for `[1,8]` returned finite float32 outputs `[1,3]`, `[1,1]`, `[1,8]`; the public batch self-check passed for `N=2`. Full lifecycle tests also confirmed all three ports bind and rebind. Shared hashes: checkpoint `9960f898d775cc7b984e530238f09ce0487a62684ba574475c8094fda1d18728`; README `a8aee1d6722eb6ae3a287d38f6240d92680e925e1113093d0a10579500e414e8`; init `ffb08e440a124cae2a337a231e243fb88e9f533f1303cce810b5485a2dd1f044`; network `9ab4bf3f50f353b292842429ed35ea0a26ef72a2e7a06ae9c4974c16d4511199`.
- **Supersedes / related:** none

## D-002 — Exact JSON validation and one-row-per-patient/tick persistence
- **When / milestone:** 2026-10-11 / initial design
- **Status:** Adopted
- **Requirement:** `SPEC.md` §§3–7
- **Decision:** Parse JSON constants strictly, validate positive integer IDs before coercion, normalize invalid vitals to SQL NULL, and process valid same-patient readings sequentially while persisting only the last result in a frame.
- **Why:** Python's default JSON and numeric type behavior accepts values the protocol explicitly rejects; validation at ingress makes the tick counter and records trustworthy.
- **Alternatives considered:** Rely on Flask/Python coercion and validate only ranges; rejected because `bool` is an `int` subclass and float IDs can be silently truncated.
- **Trade-offs / risks:** Custom parsing and validation increase edge-case code; bounded buffers and limits keep malformed traffic finite.
- **Implementation:** `hearth/protocol.py`, `hearth/engine.py`, and tables in `hearth/database.py`.
- **Verification:** Public checks exercised invalid IDs, malformed/nonadvancing readings, finite conversion and null outputs for invalid/boolean/overflow vitals, plus the seven-tick prediction boundary. Actual segmented 900 KB adapter input was forwarded and persisted.
- **Supersedes / related:** none

## D-003 — Persisted latest-session selection and assignment-first authorization
- **When / milestone:** 2026-10-11 / initial design
- **Status:** Adopted
- **Requirement:** `SPEC.md` §§7–8.2
- **Decision:** Resolve the latest session from persisted tick rows on every protected data query; apply guardian assignment filters before aggregates, alert caps, and patient detail selection.
- **Why:** A restart with no new frames must preserve visibility, while guardians must not infer hidden patients or sessions through aggregates.
- **Alternatives considered:** Use a process-local session variable; rejected because it loses latest persisted data after restart.
- **Trade-offs / risks:** Query implementation is more involved; consistent shared filtering helpers will reduce endpoint drift.
- **Implementation:** `current_session()` and query/visibility helpers in `hearth/database.py` and `hearth/web.py`.
- **Verification:** Public checks verified exact empty live/overview shapes, guardian filtering for lists/aggregates/detail/system, and persisted latest-session visibility after restarting with no new frame.
- **Supersedes / related:** none

## D-004 — Password hashing and Origin-first POST protection
- **When / milestone:** 2026-10-11 / initial design
- **Status:** Adopted
- **Requirement:** `SPEC.md` §8.1
- **Decision:** Use stdlib `hashlib.scrypt` with per-user random salt and a Flask signed session; reject all API POSTs unless exactly one Origin matches configured loopback scheme/host/port before any route logic.
- **Why:** Scrypt meets the password-specific KDF contract without another direct dependency; an app-level before-request hook gives uniform CSRF ordering.
- **Alternatives considered:** Unsalted/general-purpose hashes; route-local Origin checks. Both weaken the stated security guarantees or invite omissions.
- **Trade-offs / risks:** Scrypt parameters affect login latency; configured session key must be validated and must remain stable across restarts for sessions to persist.
- **Implementation:** `hearth/security.py` and the Origin-first Flask hook and auth routes in `hearth/web.py`.
- **Verification:** Public checks verified scrypt-backed bootstrap/login, guardian-only public signup, missing/mismatching Origin rejection, admin assignment ID validation, guardian restrictions, and GET logout 405.
- **Supersedes / related:** none

## D-005 — Single-agent execution and supplied model boundary
- **When / milestone:** 2026-10-11 / initial inspection
- **Status:** Adopted
- **Requirement:** `RULES.md` §4; `SPEC.md` §11
- **Decision:** Complete this build with one primary instance and no delegates. Treat `shared_model/` as read-only and use only its documented `load_model()` interface.
- **Why:** Single-agent work is permitted and avoids model-routing ambiguity under the exact-version rule.
- **Alternatives considered:** Delegation; not needed for this build.
- **Trade-offs / risks:** All implementation and review work is serial. Platform-visible exact model build/version and token metrics are unavailable to this workspace; report them as unknown for operator verification.
- **Implementation:** Primary instance only; exact assigned runtime version unknown from exposed interface.
- **Verification:** Supplied model imported and tested as recorded in D-001; all four file hashes were rechecked after implementation and match the initial values. No shared dependency edits occurred.
- **Supersedes / related:** none

## D-006 — Runtime validation before listener startup
- **When / milestone:** 2026-10-11 / initial design
- **Status:** Adopted
- **Requirement:** `SPEC.md` §2
- **Decision:** Validate all specified environment strings in the launcher before spawning any listener; bind TCP sockets with `SO_REUSEADDR`; supervise children and forward SIGTERM with bounded cleanup.
- **Why:** This provides deterministic rejection of invalid configuration and immediate port reuse.
- **Alternatives considered:** Allow each service to validate after startup; rejected because one listener could bind before a later validation error.
- **Trade-offs / risks:** Launcher logic is security/lifecycle critical and needs direct subprocess checks.
- **Implementation:** `hearth/config.py`, `hearth/launch.py`, and executable `start.sh`.
- **Verification:** Public checks rejected empty and forbidden simulator values, out-of-range/reserved dashboard ports and empty session keys before listener launch; readiness, SIGTERM shutdown, immediate port reuse, and simulation-on tick production passed.
- **Supersedes / related:** none

## Assumptions and deviations

| ID | `SPEC.md` reference | Assumption / deviation | Reason | Status / verification |
|---|---|---|---|---|
| A-001 | §2 | Current workspace exposes `python3` but not `python`; `start.sh` still invokes the required `python` command. | Keep the launcher aligned with the evaluator environment instead of changing global interpreter aliases. | Verified limitation: local suite ran with a temporary PATH alias to Python 3.12.9; launcher readiness/lifecycle passed. |

## D-007 — Local-only UI and dependency set
- **When / milestone:** 2026-10-11 / implementation complete
- **Status:** Adopted
- **Requirement:** `SPEC.md` §§1, 8–9
- **Decision:** Bundle the dashboard as server-rendered HTML plus local CSS and vanilla JavaScript; implement charts with canvas and use no external CDN or direct runtime dependency beyond the allowed pinned packages.
- **Why:** This meets the functional dashboard requirement without a frontend framework or runtime network service.
- **Alternatives considered:** A remote chart CDN or frontend framework; both conflict with offline/security constraints or stack rules.
- **Trade-offs / risks:** The hand-built charts are intentionally simple, and visual accessibility was not independently assessed in a browser.
- **Implementation:** `hearth/templates/`, `hearth/static/`, `requirements.txt`.
- **Verification:** `node --check` passed for both JavaScript files; dashboard routes were exercised through HTTP readiness and API workflow self-checks.
- **Supersedes / related:** none

## D-008 — Reproducible public self-check result
- **When / milestone:** 2026-10-11 / final verification
- **Status:** Adopted
- **Requirement:** `RULES.md` §§2, 5; `SPEC.md` §§2–3, 8–11
- **Decision:** Run the standard pytest suite with a temporary `python` PATH alias because the workspace lacks that command, while keeping `start.sh` on the evaluator-required `python` command.
- **Why:** It executes the exact requested test invocation on the provided Python 3.12.9 interpreter without changing global state.
- **Alternatives considered:** Modify system PATH/interpreter setup; unnecessary and out of scope.
- **Trade-offs / risks:** The alias is local to verification; clean evaluator environments must provide `python` as specified.
- **Implementation:** Self-checks in `tests/public/test_contracts.py`.
- **Verification:** `PATH=/private/tmp/hearth-python-bin:$PATH python -m pytest tests/public` on 2026-10-11: **9 passed, 0 failed, 0 skipped** in 6.14 seconds. The run used an escalation after the sandbox denied loopback binding. Python compile and Node syntax checks passed.
- **Supersedes / related:** D-001, D-006

## Agent and usage record

| Instance / invocation ID | Exact model ID/version | Role and assigned tasks | Start/end time and overlap | Handoff/review outcome | Input/output tokens |
|---|---|---|---|---|---|
| Primary-1 | GPT-6 family; exact ID/version unavailable in exposed runtime metadata | Primary: inspect, implement, debug, self-review | 2026-10-11T06:51Z–2026-10-11T07:04Z; no overlap | No delegates invoked | Unknown |

**Peak concurrent agents:** 1
**Lifetime agent invocations:** 1
**Total primary + subagent + reviewer tokens:** Unknown; platform usage metrics unavailable.

## Significant debugging and test log

| Milestone / time | Issue or failed test | Investigation and attempts | Resolution or remaining blocker | Evidence |
|---|---|---|---|---|
| Initial inspection, 2026-10-11 | `python` command not found | Confirmed `python3` is Python 3.12.9 and imports Flask, Torch, NumPy, and supplied dependency. | Used a temporary PATH alias for the required standard test command; kept launcher contract unchanged. | Final test command and result under D-008. |
| Early test run, 2026-10-11 | First seven-tick inference self-check raised `NameError: json` | Prediction code loaded persisted activity JSON but had omitted the import. | Added the standard-library import; prediction self-check then passed. | Final nine-test suite under D-008. |
| Early integration attempt, 2026-10-11 | Sandbox refused binds with `PermissionError: Operation not permitted` | Requested escalated execution for loopback service lifecycle tests. | Approved execution allowed the services to bind; readiness, shutdown, and immediate rebind passed. | Final nine-test suite under D-008. |
| Test refinement, 2026-10-11 | Vital-null API assertion inspected the latest tick while invalid values were placed on tick 1 | The test correctly returned the latest tick's finite values. | Moved invalid values to tick 7 so the API assertion checks the contract's latest row; implementation unchanged. | Final nine-test suite under D-008. |

## Standard contract decisions and verification

- SQLite path: `$HEARTH_DATA_DIR/hearth.db`; startup creation, persistence, restart visibility verified.
- Admin bootstrap: scrypt salted hash, idempotent existing-admin behavior and guardian collision failure implemented; bootstrap, login and restart behavior passed. Existing-admin unchanged-password and collision paths are implemented but not separately asserted by public tests.
- TCP adapter: incremental JSON-array parsing, 1 MiB cap and five-second inactivity timeout implemented; segmented near-limit input passed. Oversize and timeout paths were not separately timed in the public suite.
- Validation: strict frame/readings validation including float patient IDs and IDs above `2^63-1`; invalid/overflow vitals normalize to null; public self-checks passed.
- Environment: empty and forbidden simulator values, out-of-range/reserved dashboard port, and empty session key are rejected before listeners; public self-checks passed.
- Activity: missing/invalid values map to zero for model input; active maps to 3; public helper checks passed. Valid received values are stored in JSON form.
- Current session: latest persisted session selection and exact empty response contracts passed after restart.
- Shared model: documented interface and CPU `N=1` and `N=2` inference passed; package SHA-256 values recorded under D-001.
- Origin: signup missing and mismatching Origin were rejected before payload handling; code hook covers all POST `/api/*` routes.
- Guardian aggregates: patient lists, current-session totals, patient detail, and system authorization filtering passed.

## Final submission record

| Item | Value |
|---|---|
| Verified implementation commit SHA | `ac569a1bb9eb7d28443a86b169e66345431bdc21` |
| Final documentation commit SHA | Reported in the completion response; this field is intentionally non-self-referential |
| Public self-test command and actual outcomes (`python -m pytest tests/public`) | 2026-10-11: 9 passed, 0 failed, 0 skipped in 6.14 seconds; exact command and alias details in D-008 |
| Outstanding issues and known limitations | No visual browser accessibility review; simulator distributions and long-duration behavior not measured; application is synthetic-data-only and nonclinical |
| Development milestones completed | Requirements/model inspection; application, UI, persistence and tests implemented; final self-checks passed |
