# S3 addendum (recorded before S4 starts)

## 1. Gate count reconciliation (correction of the S3 report)
The S3 report stated "all 12 pre-registered gates pass". That number was wrong. `s3_criteria.json` contains **14 criteria**:

| Kind | Count | IDs |
|---|---|---|
| gate (decides the verdict) | **11** | L1, I1, Q1, Q2, U1, U2, U3, S1, R1, P1, C1 |
| constraint (reported, not a pass/fail gate) | 1 | L2 (paper/live use of derived signals) |
| report-only | 2 | S2 (survivorship per cohort), T1 (time dimension) |

The gate table in the S3 report listed exactly these 11 gates plus the three non-gating rows; `s3_audit_result.json` evaluates 11 gates (`failed: []`, verdict CONDITIONAL_GO). The verdict is unchanged; only the sentence "12 gates" is corrected to **11 gates (14 criteria)**.

## 2. Final CI outcome on commit 1975df7 (Freqtrade CI run 45784252631, checked 2026-11-26)
| Result | Jobs | Classification |
|---|---|---|
| success | 20 (all Linux, Windows and macos-26 test jobs, Online/live tests, Pre-commit checks, mypy/docs jobs) | code OK |
| skipped | 5 (Docker, PyPI publish, notify) | expected |
| cancelled | 3: `Tests and Linting (macos-15, 3.12 / 3.13 / 3.14)` | **infrastructure**: no runner was ever assigned (no `runner_name`, no steps run) |
| failure | 1: aggregate `Build (3.13)`, failing step "Decide whether the needed jobs succeeded or failed" | **infrastructure-derived**: it fails only because the three macos-15 jobs it depends on were cancelled; no test or lint job failed |
Quant CI (run 45784252558), zizmor (45784252531) and Pre-commit checks: success. Code failures seen earlier in the S3 sequence were real and fixed: mypy annotations in `s3_scripts/analyze.py` (`adeaf65` -> `a14e7f9`), Windows UTF-8 / CRLF in new tests (`a14e7f9` -> `1975df7`).
