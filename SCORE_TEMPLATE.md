# SCORE TEMPLATE — Hearth AI Implementation Benchmark

**Public rubric | Stage A | To be completed by the evaluator, not self-awarded by a builder**

The same rubric and independently frozen test cases apply to each model's single final submitted build. This file is **visible to all models**; hidden test implementations and expected answers are **not** supplied.

## 1. Evaluation record

| Field | Value |
|---|---|
| Assigned model ID / exact version (all agents) | TBD |
| Verified model routing / fallback check (operator logs) | TBD / unavailable |
| Peak concurrently active agents (max 3) | TBD / unavailable |
| Total agent instances/invocations (including replacements) | TBD / unavailable |
| Implementation repository | TBD |
| Submission | Final frozen commit |
| Git commit SHA | TBD |
| Date / evaluator | TBD |
| Hardware / OS / dependency versions | TBD |
| Shared checkpoint/inference artifact hash | TBD |
| Actual monetary cost | TBD / unavailable |
| Measured primary input/output tokens | TBD / unavailable |
| Measured subagent and review input/output tokens | TBD / unavailable |
| Combined tokens, all agents/reviews (primary cost figure) | TBD / unavailable |
| API-equivalent cost | TBD (method) / unavailable |
| Elapsed development time / human interventions | TBD |

## 2. Primary outcome: raw test results

**Raw passed / total eligible tests is the primary report.** Record each category's failures and evidence separately; "not run" is not "passed". The evaluation team defines and freezes the concrete tests, category mapping and performance workload *before* examining results. Tests are run on the same environment and common fixtures. The independent harness starts `./start.sh` from the repository root with the approved `python` environment. It requires HTTP/TCP readiness within 60 seconds, verifies shutdown of every child process and listener within 10 seconds of SIGTERM, **immediate rebind/restart** on the same ports, and rejection of invalid simulator environment values. It tests segmented/malformed adapter and AI-server inputs, rejects float/bool, out-of-range and >`2^63-1` patient IDs (including assignment), and checks that nonnumeric/boolean or float64-overflow vital values are returned as `null`. It also tests rejection of empty or nonconforming simulator environment formats and of an invalid dashboard port or empty session key. It also verifies that **`$HEARTH_DATA_DIR/hearth.db`** exists and persists, but evaluates patient records and security through the **public HTTP/TCP contracts**, without assuming internal table or column names. It uses `HEARTH_ADMIN_USER` / `HEARTH_ADMIN_PASS` for headless authentication, and supplies the canonical `Origin: http://127.0.0.1:<port>` on **every API POST request**. It tests that absent/mismatching origins return 403 and do not mutate state. Builder-written tests in `tests/public/` are **self-checks** and are not part of the scored independent test suite unless the evaluator separately freezes identical copies for all arms.

| Category (`SPEC.md` reference) | Passed | Total | Skipped / not run | Failure details or evidence |
|---|---:|---:|---:|---|
| Launch and reproducibility (§§1–2, 14) | — | — | — | — |
| Sensor, simulator, TCP and adapter (§§3, 10) | — | — | — | — |
| Persistence and REST data (§§7–8.2) | — | — | — | — |
| Classification and **seven-tick** risk (§§4–6, 11–12) | — | — | — | — |
| Authentication, role security and patient isolation (§§8.1, 13) | — | — | — | — |
| Dashboard workflows (§9) | — | — | — | — |
| Fault handling / reliability (§§2–3, 7, 10) | — | — | — | — |
| **Total** | **—** | **—** | **—** | **—** |

## 3. Secondary summary score (optional, out of 100)

Use **only if all category test counts and mappings were frozen before testing**. Within each category: `category points = category weight × (tests passed / total frozen required tests)`. A skipped or unrun required test earns **zero** points and remains separately marked as not run; an invalid test must be documented and handled consistently across all arms. Report to one decimal place; no arbitrary partial credit. If no required tests were defined in a category, mark the weighted score **N/A** rather than silently redistributing weights. **Do not use this score as a substitute for raw test results or safety gates.**

| Category | Weight | Achieved points |
|---|---:|---:|
| Launch and reproducibility | 10 | — |
| Ingestion, framing, simulator and adapter | 15 | — |
| Storage and REST API correctness | 20 | — |
| ML integration and seven-tick risk behavior | 20 | — |
| Authentication and authorization security | 20 | — |
| Dashboard functionality | 10 | — |
| Reliability / fault handling | 5 | — |
| **Total** | **100** | **—** |

**Mandatory security gate:** Provision the admin using the standard bootstrap environment variables without manual intervention. Independently report **PASS / FAIL / NOT RUN** for (a) unauthenticated patient-data access, (b) guardian accessing unassigned patients or aggregate data (including `/api/live`, `/api/overview`, leaderboard and tick statistics), (c) public admin escalation, (d) Origin-based CSRF enforcement on API POST actions, (e) admin-only `/api/system`, and (f) GET logout having no state-changing effect. **Any confirmed critical failure means "not security-ready" regardless of numeric score.** Do not use real patient data.

## 4. Performance and engineering observations (unweighted)

| Metric | Result | Workload / method |
|---|---|---|
| Median / p95 tick processing latency | TBD ms | Same machine; defined frame size |
| Median / p95 HTTP response latency | TBD ms | Same requests / warm-up |
| Sustained rate / dropped frames | TBD | Same synthetic load |
| CPU / peak memory | TBD | Same sampling and environment |
| UI accessibility findings | TBD | Same automated checks and manual criteria |
| Maintainability / code quality issues | TBD | Concrete findings with file/line references |
| Known failures, crashes or data integrity issues | TBD | Reproducible steps |

No artificial performance cutoff is implied by the specification: report measured results and any acceptance threshold **only if it was frozen before the runs**.

## 5. Final outcome, effort and cost

| Metric | Final observed result | Notes / evidence |
|---|---|---|
| Tests passed / total | — | — |
| Security gate | — | — |
| Weighted summary / 100 (if valid) | — | — |
| Elapsed development time | — | — |
| Number of prompts or agent runs (if available) | — | — |
| Peak simultaneously active agents (1–3, including primary), operator-verified | — | — |
| Lifetime agent instances/invocations, including replacements | — | — |
| Exact model/version used by every instance and any routing/fallback violations | — | — |
| Primary + subagent + reviewer input/output tokens, individually and combined (if available) | — | — |
| Actual out-of-pocket spending | — | — |
| API-equivalent estimated cost (if supportable) | — | — |
| Quota limits / incomplete scope | — | — |

**Agent fairness and cost:** The study compares **independent, unaided builds using up to three cooperating instances of a single assigned exact model/version**, not three identical single-agent trials. The limit is **three simultaneously active instances, including the primary**; total instances over time may exceed three through replacement. Any model-tier upgrade, alternate version or fallback invalidates the strict same-model condition and must be disclosed as a protocol violation, not silently counted. The operator independently records model routing, peak concurrency, all invocation counts and measured tokens from available platform/tool logs; builders also report them in `DECISIONS.MD`. **Count all primary, subagent and reviewer tokens** and attributable tool usage toward elapsed effort, credit consumption and cost estimates. Mark missing usage as unknown rather than zero. Different agent counts and quotas are potential confounders and must be disclosed, not treated as equal-resource trials.

**Interpretation rules:** Evaluate each final frozen submission only, with no follow-on fixes based on evaluator findings. Subscription usage is not the same as zero inference cost; distinguish cash spending from API-equivalent estimates, and explicitly mark unknown quantities. Document quota exhaustion and incomplete features rather than guessing.

## 6. Evaluation notes

- **Key successful behaviors:** TBD
- **Most consequential failures (with reproduction):** TBD
- **Development issues, independent fixes and remaining blockers:** TBD
- **Material deviations or confounders (agent tooling, available quotas, model versions):** TBD
- **Overall conclusion, limited to the tested application and workflow:** TBD
