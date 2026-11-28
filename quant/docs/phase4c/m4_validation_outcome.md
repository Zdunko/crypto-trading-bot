# M4 validation outcome (CI, job level) — recorded before the M4 acceptance record

Head `beb8814` (final M4 commit).

| Workflow / run | Result |
|---|---|
| Freqtrade CI #69 (run 46049585060), attempt 1 | 29 jobs: **20 success, 5 skipped, 3 cancelled, 1 failure** |
| Quant CI #139 | success |
| zizmor #69 | success |
| Pre-commit (job inside the Freqtrade matrix) | success |

- **Success (20):** `Pre-commit checks`, `Mypy Version Check`, `Documentation build`, `Online / live tests (3.14)` and every `Tests and Linting` job on ubuntu (22.04, 24.04, 24.04-arm, 26.04), windows (2022, 2025) and **macos-15** (3.12, 3.13, 3.14) for the matrix Python versions.
- **Skipped (5), by design on pull requests:** `Docker Package Cleanup`, `Docker Build and Deploy`, both `Publish Python distribution` jobs, `Notify CI Completion`. Skipped is **not** passed.
- **Unresolved infrastructure limitation (3):** `Tests and Linting (macos-26, 3.12)`, `(macos-26, 3.13)`, `(macos-26, 3.14)` were cancelled (no runner). They are **not passed tests**. On the previous head `d872b7f` the cancelled jobs were the three `macos-15` jobs and `macos-26` passed; on `beb8814` the three `macos-15` jobs passed. No macOS job has ever reported a test failure; the platform affected by the runner shortage changes from run to run. Per the owner's instruction they are not rerun repeatedly; full CI validation remains mandatory before any production deployment.
- **Aggregate `Build (3.13)`:** fails only because of the three cancelled jobs; no test failed.
- Earlier M4 commit `70f36f1` showed the same aggregate failure on a superseded run (cancelled by the next push); not a code failure.
