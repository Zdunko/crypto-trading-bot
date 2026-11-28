# S7 validation outcome (CI) — recorded before the S7 acceptance record

| Run | Head | Result |
|---|---|---|
| Freqtrade CI #57, attempt 1 | `c3ce81b` | 1 failure: `Tests and Linting (windows-2025, 3.14)`, upstream test `tests/freqtradebot/test_integration.py::test_dca_order_adjust[2]` (`assert 7 == 6`; order timestamps 22:54:59 / 22:55:00 straddle a minute boundary). That job: 1 failed, 5556 passed, 24 skipped (all `quant/tests` passed). Aggregate `Build (3.13)` failed as a consequence; the other upstream matrix jobs were cancelled by the matrix failure. Quant CI, zizmor, Pre-commit passed. |
| Freqtrade CI #57, attempt 2 (rerun of failed jobs) | `c3ce81b` | cancelled by the workflow concurrency group when the S8 pre-registration commit `a54ff97` was pushed. **Not a validation result** (recorded as such). |
| Freqtrade CI #59 | `bdd47cf` | **all 24 jobs success, 5 skipped** (publish/docker jobs), including all six Windows jobs (2022 and 2025, Python 3.12/3.13/3.14), `Pre-commit checks`, `Build (3.13)`; Quant CI #118 and zizmor #59 success. |

Between `c3ce81b` and `bdd47cf` no upstream path (`freqtrade/`, `tests/`, `.github/`, `ft_client/`, `docs/`) changed (verified with `git diff --stat`, empty). The same upstream test therefore failed once and passed once on identical upstream code: the failure is **intermittent** (timing at a minute boundary), a single observation of each, not a statistical estimate of the flake rate.

No upstream test was modified, skipped or suppressed and no CI workflow was weakened; no new commit was pushed to "kick" CI. The earlier failures on `5ffce7c`..`ba376c7` were caused by my own formatting/typing mistakes (ruff import order, mypy annotation, end-of-file newline) and are fixed in `86d9f4c`, `ba376c7`, `c3ce81b`; they are recorded, not hidden.
S7 is therefore frozen: `protocol/s7_freeze_record.json` (hashes verified by `tests/test_s7_freeze.py`) plus `protocol/s7_acceptance_record.json`.
