# Hearth AI — Implementation Benchmark

**Stage A | Builder workspace | Neutral instructions for every independent implementation**

Build the live-mode patient-monitoring application **independently** from the supplied requirements. Every builder receives identical starting materials and follows the same rules. Use **synthetic data only**. Do not inspect other implementations.

## Start here — required reading

Before writing any code, read these five files in this order:

1. **`README.md`** — workflow and required outputs (this file).
2. **`RULES.md`** — mandatory independent-development and fairness rules.
3. **`SPEC.md`** — authoritative Stage A product behavior, interfaces and security requirements (v1.0.1).
4. **`SCORE_TEMPLATE.md`** — public evaluation rubric and reporting requirements.
5. **`DECISIONS.MD`** — the decision log that **you must maintain**.

**You must follow `RULES.md` and `SPEC.md`.** `SPEC.md` controls what to build; `RULES.md` controls how you work independently; `SCORE_TEMPLATE.md` controls how results are reported. Neither this README nor your decision log authorizes deviations from them. When unclear, implement a reasonable interpretation and log it; do not silently change the rules.

## Non-negotiable developer workflow

1. Read the five files and examine the **provided shared checkpoint/inference dependency only**. Do not browse, search for, clone or inspect other implementations of this application; generic official development documentation may be consulted under `RULES.md`.
2. Work in **Python 3.10+** (Flask, SQLite) for backend/services and **HTML/CSS with vanilla JavaScript** for the frontend. Keep it local/offline; obey `SPEC.md` for APIs, TCP framing, seven-tick prediction and security.
3. **Update `DECISIONS.MD` continuously:** record each important architecture choice, implementation trade-off, assumption, workaround and specification deviation **with the reason, alternatives and relevant spec section**. Never erase superseded decisions; mark them superseded.
4. Build, run and test the required live-mode flow. Put your own self-check tests in `tests/public/`, preserve any operator-supplied tests, and run the standard command **`python -m pytest tests/public`** before final submission. Record the real results in `DECISIONS.MD` and this README. Builder-written tests are not the independent evaluation. Do not claim an unrun test has passed.
5. You may use **up to three simultaneously active agent instances** (including the primary), all using the **exact same assigned model ID and version**. This is a concurrency limit, **not three instances for the entire build**: completed agents can be replaced, but record **every instance/invocation**, its role and timing in `DECISIONS.MD`. No higher tier, alternative model/version, automatic fallback, other-model reviewer or outside human help is allowed. The operator independently verifies agent counts/model routing from available tool logs; **all primary, subagent and reviewer tokens count** toward usage and cost. Investigate blockers within the permitted same-model agent team and log significant attempts and outcomes.
6. When you believe the app is complete, **commit the final version, record the SHA and reply `DONE` on its own line**. The operator will freeze that commit for a single independent evaluation. Do not continue modifying the submission afterward.

## Deliverables in your repository

- Complete live-mode application, including simulator, AI server, device adapter, database and dashboard.
- Executable **`start.sh`** meeting the noninteractive launch/termination contract in `SPEC.md` §2; initialize the fixed SQLite file at **`$HEARTH_DATA_DIR/hearth.db`** and support the `HEARTH_ADMIN_USER` / `HEARTH_ADMIN_PASS` bootstrap pair.
- All **five** documents, with `SPEC.md`, `RULES.md` and `SCORE_TEMPLATE.md` preserved unchanged, and `README.md` and `DECISIONS.MD` updated by you.
- Local setup, run and test instructions; design notes; documented assumptions, limitations and security measures.
- A single final submitted commit SHA; earlier milestone commits are optional and may be kept for traceability.

## Required local start and public self-tests

The environment contract is in `SPEC.md` §§1–2, 7 and 8.1. For headless local evaluation, set `HEARTH_DATA_DIR` and both admin bootstrap variables, then launch the services. Use a **unique, strong temporary password** for each isolated test environment; do not store it in this README, version control or logs. The application must initialize `$HEARTH_DATA_DIR/hearth.db` and safely provision the admin before the dashboard is ready. Bootstrap is idempotent and must never elevate an existing guardian.

Run public self-checks from the project root after installing the project's development requirements (including `pytest`):

```bash
python -m pytest tests/public
```

**Evaluator launch:** From the repository root, the common environment provides `python` (Python 3.10+) and dependencies installed with `python -m pip install -r requirements.txt`. Start with `./start.sh`; `start.sh` must not install packages. With `HEARTH_SIMULATE=0`, the three services must be ready within **60 seconds** (`GET /api/auth_status` → 200 JSON; AI and adapter ports accept TCP), and terminate within **10 seconds** of SIGTERM without leaving child processes or bound ports, and permit immediate relaunch/rebinding of all three ports. The common, immutable `shared_model/` package is provided by the researcher and must not be edited.

**Open the app at `http://127.0.0.1:<HEARTH_DASHBOARD_PORT>` (not `localhost`).** All API POST requests (including headless tests) require `Origin: http://127.0.0.1:<HEARTH_DASHBOARD_PORT>`; the server rejects missing or incorrect origins with 403 before other validation.

**Builder responsibility:** create and maintain your own self-checks in `tests/public/` if none are supplied. Cover segmented adapter JSON up to 1 MiB, structurally malformed readings with no tick advancement, vital values such as `"abc"`, `true`, `1e400` or huge integer magnitudes being returned as `null`, rejection of `patient_id: 1.0` or patient IDs above `2^63-1` (including in assignments), invalid/empty simulator environment variables, forbidden numeric formats, an out-of-range dashboard port or an empty session key causing startup failure, immediate port reuse after restart, blank/invalid activity mapping to zero, empty overview/live responses, and latest-persisted-session behavior after restart. If the operator supplies common public tests, retain and run them unmodified. Write down the command, date, passed/failed/skipped counts and any unresolved failures in `DECISIONS.MD` and below. A missing `tests/public/` directory or an unrun command is **not** a passing result. The evaluator runs a separate frozen test suite; self-written tests do not determine the comparative score.

## Developer-maintained project notes (fill these in)

**Model / agent version:** _Not recorded yet_  
**Exact assigned model ID/version for all agents:** _Not recorded yet_  
**Peak concurrently active instances (≤3), lifetime instances, roles/delegation:** _Not recorded yet_  
**Primary/subagent/review token usage (include all invocations, if available):** _Not recorded yet_  
**Commit / branch:** _Not recorded yet_  
**Shared inference dependency version or hash:** _Not recorded yet_  
**Prerequisites and installation:** _To be added_  
**How to start (`HEARTH_DATA_DIR`, `HEARTH_ADMIN_USER`, `HEARTH_ADMIN_PASS`, `HEARTH_SIMULATE`, etc.):** _To be added; do not include real secret values_  
**SQLite database path:** `$HEARTH_DATA_DIR/hearth.db`  
**Public self-test command:** `python -m pytest tests/public`  
**Actual test results (date, passed/failed/skipped):** _Not yet run_  
**Key implementation decisions:** _Refer to entries in `DECISIONS.MD`_  
**Assumptions, deviations and known limitations:** _To be added_  
**Current milestone / completion status:** _Not started_  
**Final submitted commit SHA:** _Not yet created_

> This is a synthetic-patient engineering demo, **not** a validated clinical system or medical device.


