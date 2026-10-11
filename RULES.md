# RULES — Hearth AI Implementation Benchmark

**Mandatory for every builder. Apply these same rules to every independent implementation.**

## 1. Sources and starting conditions

- Start from the identical researcher-provided repository, `SPEC.md`, fixed checkpoint and shared inference dependency. The fixed package belongs in `shared_model/` and must provide the import contract in `SPEC.md` §11; do not start runs until the researcher supplies and verifies it. **Do not visit, browse, search for, clone or copy any other Hearth AI implementation**, whether public or private (including mirrors, cached copies and code search). Generic official programming and dependency documentation is allowed. The supplied inference dependency is the only shared application-specific code.
- The supplied shared inference dependency may expose only the model architecture, checkpoint loading and its output interface; it must **not include** application preprocessing, server, database or UI logic. Do not change the model weights or shared dependency. No model training, external AI services, external databases or online runtime dependencies. No real patient data; synthetic data only.
- Use **Python 3.10+ / Flask / SQLite** for backend, **HTML/CSS + vanilla JavaScript** for frontend. Follow the root-working-directory, `python` interpreter, 60-second readiness, 10-second SIGTERM and immediate-port-reuse lifecycle contract in `SPEC.md` §2. Only the dependencies allowed in `SPEC.md` §1 may be used; declare pinned requirements in `requirements.txt` and **do not install packages in `start.sh`**. Local standalone charting libraries are allowed, not frontend app frameworks. Reject invalid `LIVE_N_PATIENTS` / `LIVE_TICK_SECONDS` at startup rather than clamping, including empty strings and numeric formats forbidden in `SPEC.md` §2, and reject an invalid `HEARTH_DASHBOARD_PORT` or empty `HEARTH_SESSION_KEY` the same way. Enforce the 64-bit positive-integer patient-ID bound and reject float64-overflow vitals safely, as specified in §§3 and 8. Store all required application tables in **`$HEARTH_DATA_DIR/hearth.db`**, support the secure headless admin bootstrap pair `HEARTH_ADMIN_USER` / `HEARTH_ADMIN_PASS`, and implement the APIs, ports, framing, launch contract and seven-**tick** behavior from `SPEC.md`. The app must operate locally without external network services/CDNs.
- No scope additions that displace required Stage A features. Out-of-scope tasks in `SPEC.md` are not scored.

## 2. Documentation is part of the deliverable

- Read `README.md`, **this file**, `SPEC.md`, `SCORE_TEMPLATE.md`, and `DECISIONS.MD` before coding.
- **Log important choices promptly in `DECISIONS.MD`, not retrospectively at the end.** Include the decision, why, alternatives, spec reference, consequences and verification. Log assumptions and deliberate deviations explicitly.
- Keep `README.md` updated with reproducible setup/run/test commands, what actually works, evidence, known defects and all implemented security controls. Create self-checks under `tests/public/` and run **`python -m pytest tests/public`** before final submission; log the actual command and outcome in `DECISIONS.MD`. Preserve any common operator-supplied public tests unmodified. Never report tests as passed without running them.
- Do **not edit** `SPEC.md`, `RULES.md` or `SCORE_TEMPLATE.md`; only the operator may publish a versioned revision, identically to all builders. Do not rewrite earlier decision entries: mark changed choices as superseded.

## 3. Required security

- Implement the stronger authentication and authorization required by `SPEC.md` §§8.1, 13 (including the **SameSite=Strict + exact-Origin check on all API POST requests**, POST-only logout, admin-only `/api/system`, and guardian-only aggregates): guardian-only public signup, private admin provisioning, protected patient endpoints, assignment-aware data filtering, secure password hashing, safe session cookies and CSRF defense.
- These are **mandatory requirements**. Document how they were satisfied. Use synthetic data only; no hardcoded passwords or committed secrets.

## 4. Independent development and debugging

- **Agent allowance:** At most **three simultaneously active coding agent instances**, **including the primary**, may work on a build. This cap concerns **concurrent active instances, not total instances over the project lifetime**; replacements after an instance finishes are allowed, and *every* invocation must be recorded. The primary, all subagents and any reviewer/critic must use the **same exact assigned model ID and version** throughout the run, not merely the same model family. **Never use a stronger model tier, alternate version, model auto-fallback, outside reviewer, different model, competing implementation or human for code, diagnoses or feedback.** Disable routing/fallback if possible; if the environment cannot guarantee the model ID/version, do not invoke that agent and report the blocker. Agents may implement, debug, review and coordinate within the same build. Log model IDs/versions, agent invocations, roles, start/end times, maximum concurrency and available token usage in `DECISIONS.MD`; the **operator also audits model routing, concurrency and usage from platform/tool logs**. Counts from logs supersede unsupported self-reporting. Primary, subagent and review tokens **all count** toward usage/cost; unavailable token metrics must be marked unknown, not zero. A single-agent build is fully permitted.
- The operator may provide the same fixed files to every builder, start sessions and collect logs. The operator must not write or repair code or provide builder-specific technical guidance.
- When blocked, investigate and attempt fixes independently. Log significant failures, debugging attempts, outcomes and unresolved blockers in `DECISIONS.MD` and `README.md`. Do not claim an unrun test passed.

## 5. Final submission and reproducibility

1. You may make milestone commits while building and debugging. Keep the decision log updated as you go.
2. When you believe the work is complete, run **`python -m pytest tests/public`**, record the actual passed/failed/skipped counts in `DECISIONS.MD` and `README.md`, then commit the application and documentation and record the **final commit SHA** in `README.md`.
3. Reply **`DONE`** on its own line. The operator will freeze this exact commit and run **one independent final evaluation**. Do not make changes after submission.

- Use the same published requirements, test commands, CSRF header contract and operator-set resource caps as the other builders. Ensure your public tests send the matching `Origin` header for every API POST request. No access to hidden evaluation tests. Report failures honestly; do not alter shared fixtures to make tests pass.
- Respect a **$0 additional personal-spending** policy: use only explicitly approved subscription capacity/eligible credits; never enable paid overages. If blocked by quota or absent assets, document and submit the incomplete state honestly.

## 6. What counts as completion

- Complete the live-mode Stage A system and the secure-user flows in `SPEC.md`; do not represent an untested or incomplete system as working.
- Commit implementation and documentation, including the decision log and README status. Report the exact final commit SHA, actual test results and unresolved defects.
- This is a controlled, synthetic-data software experiment, **not** a clinically validated tool.
