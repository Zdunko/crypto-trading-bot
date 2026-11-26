# S5-infra report (infrastructure, integration, synthetic validation, preparatory investigations)

Scope and boundaries: `s5_scope.md`. Criteria pre-registered in `s5_criteria.json` (commit `03af3d9`) before any S5 work; none changed. **The original S5 ("first new family evaluation") requires a market evaluation of a new family, which is prohibited, and was NOT executed.** No market backtest, no strategy optimisation, no Family B, no holdout access, no paper/live, no paid service; T1-T10, S2 risk parameters, frozen manifests and all historical results are unchanged.

## 1. Preparatory items (P1-P7)
| Item | Deliverable | Result |
|---|---|---|
| P1 S4 freeze | `protocol/s4_freeze_record.json` (dataset hash `462288b1...`, sha256 of all 10 dataset files, manifest parts, S4 criteria hash equal to the one at pre-registration `58ba372`, code hashes, provenance) + `tests/test_s4_freeze.py` (4 tests) | done; the test fails if any dataset file, the criteria, the reports or the S4 builder code changes |
| P2 limitations | `s4_limitations_register.md`: 15 entries; the 6 cancelled macOS jobs are **L-CI-MAC: unresolved infrastructure limitation, macOS untested, not passed tests** | done; no S4 criterion edited |
| P3 X1 | `s5_investigations.md` section 1, `s5_x1_investigation.json` | all 1 029 months classified (589 full-day hourly smaller, 219 hourly greater, 219 explained by hourly gaps, 2 day-missing); concentrated in 5 months (2020-12, 2021-01, 2021-04, 2021-12, 2022-04), matching periods of the upstream "fixed inconsistent data" log (hypothesis, unproven); **0 of 21 139 eligibility decisions change** if hourly-derived volume replaces daily volume (two variants); execution impact is not bounded (day-level errors -26 % / +7.6 %, 79 % hourly smaller) and stays an assumption |
| P4 identity | `s5_investigations.md` section 2, `s5_identity_review.json` | all 43 breaks reviewed with candle evidence (24 rescale signature, 3 volume surge, 16 other/insufficient); conservative handling removes only 15 of 21 139 decisions (0.07 %, 5 symbols); S4 unchanged; a v2 would need an announcement-based identity table |
| P5 holdout statement | `s5_holdout_isolation_statement.md` | supported claims (no holdout candle/price/volume read; S4 request audit and store audit) separated from exposures: S1 listing keys/sizes and `last_month` to 2026-10, S3 use of that table for survivorship reporting, 183 post-cutoff symbol names in the S4 root listing, request-log gap; explicit "not claimed" list |
| P6 licensing roadmap | `s5_production_data_licensing_roadmap.md` | phases R0-R4 with gates, written-question list, evidence ledger; nothing purchased or assumed |
| P7 scope | `s5_scope.md` | original S5 identified as a prohibited activity; plan items S3 (feasibility-gate tool) and S4 (benchmark add-ons) of the original numbering remain **not done** |

## 2. Infrastructure and integration (L1-L7)
New code (not part of the frozen S4 builder): `quantlab/pit_loader.py`, `quantlab/universe_guard.py`, `quantlab/budget.py`, `protocol/research_budget.json`, step added to `scripts/check.sh`.
- **Loader**: opens only if the dataset tables hash to the manifest and the manifest to the freeze record; serves completed candles only (`open + interval <= as_of`), never opens files of months after `as_of`, verifies every stored file's sha256 against the manifest, refuses quarantined/absent/altered/deleted data, unknown symbols, naive timestamps, dates before 2017-09 and at/after 2025-07-01. `universe_at` uses the point-in-time membership table with a staleness filter (default 3 days, an engineering assumption fixed in the criteria); `tradable` adds a freshness check on the last completed daily candle; `to_price_data` feeds the Stage 0 engine.
- **Universe guard** (`Strategy` wrapper): blocks new buys of non-members, stale assets, unknown pairs and, on any loader error, all buys, with logged reasons; sells and stops always pass; held positions are never force-sold by the guard; composes with `RiskManagedStrategy`.
- **Budget enforcement**: caps (3 further families, 3 configurations per family, N <= 52, 1 market run per family), stop rule (2 consecutive rejections under V2), `can_start_run`; `python -m quantlab.budget check` runs in `check.sh` and cross-checks N=43 against the ledger. Current state: N 43/52, 0/3 further families.
| Gate | Evidence | Result |
|---|---|---|
| L1 fail-closed (>= 9 modes) | 13 failure modes tested: freeze hash, tampered table, tampered freeze file, unknown symbol, unknown threshold, holdout dates (3), pre-window and naive timestamps, quarantined month, absent month, altered file, deleted file, missing store, stale member | pass |
| L2 causality (>= 20 cases) | 24 seeded (symbol, as_of) cases x 2 intervals: results identical when every later month file is deleted or corrupted; only completed candles returned | pass |
| L3 determinism | repeated loads equal; the Stage 0 engine hash through the loader is identical in two separate processes | pass |
| L4 guard integration | blocked reasons, sells/stops pass, held positions kept, loader error blocks buys, transparent hash equality with the unguarded run, deterministic composition with the risk wrapper | pass |
| L5 budget | every cap, the stop rule, can_start_run, real state (N=43, 0 families) and ledger cross-check, wired in `check.sh` | pass |
| L6 no network, no regression | loader/guard tests run with `socket.socket` replaced by a raising stub; full suite 540 passed (was 509); `verify_all`, S2 and S4 freeze tests pass | pass |
| L7 CI | see the PR checks of the final commit; the cancelled macOS jobs are recorded as L-CI-MAC | see chat report |

## 3. Remaining risks
Those in `s4_limitations_register.md` (licence ceiling, identity, liquidity, one cycle, X1, request-log gap, post-cutoff names, classification), plus: (a) execution-side effect of the X1 discrepancy is unbounded; (b) the 3-day staleness default is an assumption; (c) the guard blocks entries only, so a stale held position is the risk layer's problem (no automatic exit); (d) feasibility-gate tool and benchmark add-ons from the original plan are still missing, so a family evaluation cannot start even if approved; (e) macOS untested.

## 4. Recommendation
**GO for S5-infra** (research-only infrastructure; synthetic validation complete). **NO-GO, pending your explicit decision**: the original S5 (any market evaluation of a new family), Family B, holdout access, paper/live, any paid service. Suggested next approvals, in order: (1) the plan's feasibility-gate tool and pre-registration template, (2) benchmark add-ons, (3) only then a pre-registered family and its single approved run.
