# S9 validation outcome (CI, job level) — recorded before the S9 acceptance record

Head `56e6941` (final S9 commit).

| Workflow / run | Result |
|---|---|
| Freqtrade CI #64 (run 45951201492) | conclusion **success**: 29 jobs, **24 success, 5 skipped, 0 failed, 0 cancelled** |
| Quant CI #128 | success |
| zizmor #64 | success |
| Pre-commit Types update #64 | skipped by its own workflow condition (not a check on this change) |

Success (24): `Pre-commit checks`, `Build (3.13)`, `Mypy Version Check`, `Documentation build`, `Online / live tests (3.14)` and every `Tests and Linting` job on ubuntu (22.04, 24.04, 24.04-arm, 26.04), macos (15, 26) and windows (2022, 2025) for the Python versions in the matrix.
Skipped (5), by design on pull requests: `Docker Package Cleanup`, `Docker Build and Deploy`, both `Publish Python distribution` jobs, `Notify CI Completion`. Skipped is **not** passed and is not counted as a test result.

Earlier S9 commits `60cce9b`, `fd79ac1`, `51a209c` showed an aggregate `Build (3.13)` failure: each was superseded by the next push, whose concurrency group cancelled the matrix. These are cancellations by my own consecutive pushes, not code failures; the final commit ran the whole matrix undisturbed.
