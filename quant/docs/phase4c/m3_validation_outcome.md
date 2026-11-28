# M0-M3 validation outcome (CI, job level) — recorded before the M3 acceptance record

Head `d872b7f` (final M0-M3 commit).

| Workflow / run | Result |
|---|---|
| Freqtrade CI #67 (run 46002095204), attempt 1 | 29 jobs: **20 success, 5 skipped, 3 cancelled, 1 failure** |
| Freqtrade CI #67, attempt 2 (single rerun of the failed/cancelled jobs) | the 3 `macos-15` jobs stayed **queued** (no runner available); the aggregate `Build (3.13)` failed again for that reason only |
| Quant CI #135 | success |
| zizmor #67 | success |
| Pre-commit (job inside the Freqtrade matrix) | success |

- **Success (20):** `Pre-commit checks`, `Mypy Version Check`, `Documentation build`, `Online / live tests (3.14)` and every `Tests and Linting` job on ubuntu (22.04, 24.04, 24.04-arm, 26.04), macos-26 and windows (2022, 2025) for the matrix Python versions.
- **Skipped (5), by design on pull requests:** `Docker Package Cleanup`, `Docker Build and Deploy`, both `Publish Python distribution` jobs, `Notify CI Completion`. Skipped is **not** passed.
- **Unresolved infrastructure limitation (3):** `Tests and Linting (macos-15, 3.12)`, `(macos-15, 3.13)`, `(macos-15, 3.14)` were cancelled in attempt 1 and stayed queued after the rerun because no macOS-15 runner was available. They are **not passed tests** and are not counted as such. No failure was ever reported by these jobs. Per the owner's instruction they are not rerun repeatedly; full CI validation remains mandatory before any production deployment.
- **Aggregate `Build (3.13)`:** fails only because of the three jobs above; no test failed.
- Earlier failures on `3e9753c` (pre-commit end-of-file blank line in the limitations register) and `78909ab` (unformatted acquisition script) were my own formatting mistakes, fixed in `1323410` and `d872b7f`.
