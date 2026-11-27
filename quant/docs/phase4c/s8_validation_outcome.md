# S8 validation outcome (CI, job level) — recorded before the S8 acceptance record

Head `fb4e8f9` (the final S8 commit, documentation and tests only; the S8 code was `bdd47cf`).

| Workflow / run | Result |
|---|---|
| Freqtrade CI #60 (run 45947440166) | conclusion **success**: 29 jobs, **24 success, 5 skipped, 0 failed, 0 cancelled** |
| Quant CI #120 | success |
| zizmor #60 | success |
| Pre-commit Types update #60 | skipped by its own workflow condition (not a check on this change) |

Success (24): `Pre-commit checks`, `Build (3.13)`, `Mypy Version Check`, `Documentation build`, `Online / live tests (3.14)`, Tests and Linting on ubuntu-22.04 (3.12), ubuntu-24.04 (3.12/3.13/3.14), ubuntu-24.04-arm (3.13/3.14), ubuntu-26.04 (3.14), macos-15 (3.12/3.13/3.14), macos-26 (3.12/3.13/3.14), windows-2022 (3.12/3.13/3.14), windows-2025 (3.12/3.13/3.14).
Skipped (5), by design on pull requests: `Docker Package Cleanup`, `Docker Build and Deploy`, `Publish Python distribution to TestPyPI`, `Publish Python distribution to PyPI`, `Notify CI Completion`. They are release-only jobs; skipped is **not** passed and is not counted as a test result.

Earlier S8 evidence: `bdd47cf` also had 24 success / 5 skipped (all six Windows jobs passed). The single Windows failure of `c3ce81b` (`test_dca_order_adjust[2]`) did not recur in either of the two later runs on unchanged upstream code (S7 outcome document).
