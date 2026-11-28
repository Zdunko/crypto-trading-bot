# M6-S0 — synthetic validation of the capped, volatility-targeted sleeve (no market data)

Status: **synthetic only; nothing registered; N = 45 / 52, families 1 / 3.** Task M6-S0 of Issue #2 (owner approval relayed in comment 7236751506). Frozen before the first run in commit `b5907a5` (`protocol/m6_s0_fixtures_freeze.json`: fixtures, predictions, claims C1–C5, falsification/stop rules). Results: `m6_s0_results.json`; harness `quantlab/lv_sleeve_harness.py` (minimal; reuses the frozen engine and the **unchanged, always active** Risk Management V3); tests `tests/test_m6_s0_sizing.py`. V3 limits, T1–T10 and every cap are untouched. A correct SHUTDOWN is not a software failure; it falsifies the unconditional no-shutdown claim.

## 1. Corrected claim (amendment A20)
The statement "E_max = 0.15 makes shutdown impossible by construction" is **withdrawn**. What is true: one total loss of a 15 % sleeve costs at most 15 % of equity *at that moment*. It is not a cumulative bound (replenishment: 1000 → 850 → 722.50 is a 27.75 % drawdown absent intervention), not a high-water-mark bound (equity is compared with the peak, not with the last level), not a realized-exposure bound (drift between resizes), not an integrity bound (V3 shuts down on a stale or delisted held asset whatever the loss), and the normal 3σ approximation is not a hard bound.

## 2. Fixture outcomes (13 frozen fixtures + 2 declared replacements; LV-1 and LV-2)
| Fixture | Config | Predicted | Observed | Match | min equity / HWM | max single-event loss | max realized exposure | V3 transitions |
|---|---|---|---|---|---|---|---|---|
| F01 single_total_wipeout | LV-1 | no shutdown | no shutdown | yes | 0.833 | 0.162 | 0.167 | 4 |
| F01 single_total_wipeout | LV-2 | no shutdown | no shutdown | yes | 0.833 | 0.162 | 0.167 | 4 |
| F02 repeated_wipeouts | LV-1 | shutdown | no shutdown | **NO** | 0.833 | 0.162 | 0.167 | 4 |
| F02 repeated_wipeouts | LV-2 | shutdown | no shutdown | **NO** | 0.833 | 0.162 | 0.167 | 4 |
| F03 repeated_partial_losses | LV-1 | no shutdown | no shutdown | yes | 0.842 | 0.097 | 0.165 | 7 |
| F03 repeated_partial_losses | LV-2 | no shutdown | SHUTDOWN tier3_floor | **NO** | 0.820 | 0.097 | 0.165 | 2 |
| F04 gain_then_loss_from_new_peak | LV-1 | no shutdown | no shutdown | yes | 0.836 | 0.154 | 0.194 | 4 |
| F04 gain_then_loss_from_new_peak | LV-2 | no shutdown | no shutdown | yes | 0.832 | 0.154 | 0.194 | 4 |
| F05 exposure_drift_between_rebalances | LV-1 | shutdown | SHUTDOWN tier3_floor | yes | 0.786 | 0.210 | 0.214 | 1 |
| F05 exposure_drift_between_rebalances | LV-2 | shutdown | SHUTDOWN tier3_floor | yes | 0.786 | 0.210 | 0.214 | 1 |
| F06 overnight_gap_minus_50 | LV-1 | no shutdown | no shutdown | yes | 0.904 | 0.083 | 0.167 | 0 |
| F06 overnight_gap_minus_50 | LV-2 | no shutdown | no shutdown | yes | 0.897 | 0.083 | 0.167 | 1 |
| F07 partial_fills_and_double_costs | LV-1 | no shutdown | no shutdown | yes | 0.938 | 0.053 | 0.106 | 0 |
| F07 partial_fills_and_double_costs | LV-2 | no shutdown | no shutdown | yes | 0.938 | 0.053 | 0.106 | 0 |
| F08 missing_candles_short_and_long | LV-1 | shutdown | no shutdown | **NO** | 0.974 | 0.000 | 0.167 | 0 |
| F08 missing_candles_short_and_long | LV-2 | shutdown | no shutdown | **NO** | 0.974 | 0.000 | 0.167 | 0 |
| F09 delisting_one_asset | LV-1 | shutdown | SHUTDOWN integrity | yes | 0.974 | 0.000 | 0.167 | 1 |
| F09 delisting_one_asset | LV-2 | shutdown | SHUTDOWN integrity | yes | 0.974 | 0.000 | 0.167 | 1 |
| F10 delisting_with_status_feed | LV-1 | shutdown | SHUTDOWN integrity | yes | 0.974 | 0.000 | 0.167 | 1 |
| F10 delisting_with_status_feed | LV-2 | shutdown | SHUTDOWN integrity | yes | 0.974 | 0.000 | 0.167 | 1 |
| F11 calm_regime_cap_binds | LV-1 | no shutdown | no shutdown | yes | 0.974 | 0.000 | 0.167 | 0 |
| F11 calm_regime_cap_binds | LV-2 | no shutdown | no shutdown | yes | 0.974 | 0.000 | 0.167 | 0 |
| F12 turbulent_regime_target_binds | LV-1 | no shutdown | no shutdown | yes | 0.935 | 0.000 | 0.145 | 0 |
| F12 turbulent_regime_target_binds | LV-2 | no shutdown | no shutdown | yes | 0.913 | 0.000 | 0.206 | 0 |
| F13 determinism_and_reconciliation | LV-1 | - | no shutdown |  | 0.833 | 0.162 | 0.167 | 4 |
| F13 determinism_and_reconciliation | LV-2 | - | no shutdown |  | 0.833 | 0.162 | 0.167 | 4 |
| F08a short_gap_12h | LV-1 | no shutdown | no shutdown | yes | 0.971 | 0.000 | 0.167 | 0 |
| F08a short_gap_12h | LV-2 | no shutdown | no shutdown | yes | 0.971 | 0.000 | 0.167 | 0 |
| F08b long_gap_60h_resuming | LV-1 | shutdown | SHUTDOWN integrity | yes | 0.974 | 0.000 | 0.167 | 1 |
| F08b long_gap_60h_resuming | LV-2 | shutdown | SHUTDOWN integrity | yes | 0.974 | 0.000 | 0.167 | 1 |

Claims (falsified if any fixture/config violates, rules frozen):
- **C1 no shutdown — FALSIFIED** by: F03 repeated partial losses|LV-2, F05 exposure drift between rebalances|LV-1, F05 exposure drift between rebalances|LV-2, F08b long gap 60h resuming|LV-1, F08b long gap 60h resuming|LV-2, F09 delisting one asset|LV-1, F09 delisting one asset|LV-2, F10 delisting with status feed|LV-1, F10 delisting with status feed|LV-2.
- **C2 realized exposure ≤ 0.1575 — FALSIFIED** (27 fixture/config runs; includes calm fixtures).
- **C3 single-event loss ≤ 15 % — FALSIFIED** by: F01 single total wipeout|LV-1, F01 single total wipeout|LV-2, F02 repeated wipeouts|LV-1, F02 repeated wipeouts|LV-2, F04 gain then loss from new peak|LV-1, F04 gain then loss from new peak|LV-2, F05 exposure drift between rebalances|LV-1, F05 exposure drift between rebalances|LV-2, F13 determinism and reconciliation|LV-1, F13 determinism and reconciliation|LV-2.
- **C4 drawdown from HWM < 18 % with V3 — FALSIFIED** by: F03 repeated partial losses|LV-2, F05 exposure drift between rebalances|LV-1, F05 exposure drift between rebalances|LV-2.
- **C5 entry blocked while FLAT_COOLDOWN/SHUTDOWN — not falsified** (no buy fill inside those windows; 140–210 shadow signals suppressed in the wipeout fixtures).
Guarantees C1–C4 are **withdrawn**; nothing was tuned to replace them.

## 3. What the counterexamples show (all synthetic)
1. **Single-event loss exceeds the cap** (F01/F02/F04: 0.154–0.162 > 0.15): realized exposure was 0.167–0.194 at the event because positions drift between Monday resizes and liquidation costs add. At a 1,000 USDT wallet the 5 USDT minimum notional also acts as a resize hysteresis (a 15 USDT position is only trimmed after a 33 % move; the calm fixture F11 issued 10 buys and **0 sells** and drifted to 0.167). This tolerance shrinks with account size (3 % at 10,000 USDT) but was **not re-tested** (no new fixtures after results).
2. **Drift between rebalances can breach the floor** (F05: +40 % rally then wipeout before the next Monday → loss 0.210, drawdown 0.214, SHUTDOWN `tier3_floor`, both configs).
3. **Cumulative partial losses with replenishment** (F03: five −60 % shocks): LV-2 reached tier 1 (REDUCED, whose 0.5 exposure cap does not bind a 0.15 sleeve, so replenishment continued) and then SHUTDOWN `tier3_floor` at the second shock; LV-1 survived (volatility estimate rose after the first shock, target exposure fell) with drawdown 0.158 and several tier transitions. This is a difference between the sizing concepts under one synthetic shape only.
4. **V3 integrity shutdown is independent of loss size** (F08b 60 h hole on one held asset; F09 delisting of one asset = 1.5 % of equity; F10 explicit DELISTED status — shutdown immediately instead of after 48 h): `integrity` SHUTDOWN, terminal. In the S4 dataset 83 of 411 assets failed (M4 report), so a 10+-asset basket held for years is exposed to this by construction.
5. **After the first tier-2 event the sleeve is practically dead** (F01/F02: mean realized exposure 0.023–0.028 over the run): V3 flattens, waits 14 days, re-enters with the risk-budget cap (`R/φ`, φ = 0.303), which scaled the buys to 4.4 USDT per asset (≈ 44 USDT in total); these were **rejected below the minimum notional** (120–170 rejects). That is why the second and third wipeouts of F02 did no damage (frozen prediction: shutdown — **wrong**). V3 therefore *did* block replenishment here, but through the budget cap plus the minimum notional at a 1,000 USDT wallet; at larger wallets the order would pass and the budget formula assumes a 30 % stress gap, not a total loss (allowed ≈ 44 USDT corresponds to a remaining budget R = 0.303 × 44 ≈ 13 USDT, while a total loss of 44 USDT would exceed it), so a floor breach would be possible (**arithmetic, not tested**). REENTRY also stays at its final step while d_L ≥ 15 %, which in cash cannot improve, so the sleeve stays capped.
6. **Fail-closed estimator over-reacts**: a 12 h hole in one basket asset made σ̂ NaN for 60 days and liquidated the whole sleeve (F08 as run — declared event not exercised, see §6; F08a).
7. **Cap binds or targets** (F11/F12): calm regime (σ̂ ≈ 0.29): LV-1 = LV-2 (cap binds), realised portfolio volatility 4.8 % vs target 10 % — the target is **not attainable**, only the cap; turbulent regime (σ̂ ≈ 1.12): LV-1 exposure falls to ≈ 0.10 and realised volatility is 9.8 % ≈ target; LV-2 has no target (19.2 %).
8. Costs and fills (F07, double costs, participation cap): realized exposure stayed at or below target (max 0.106), fills were delayed/partial and 156 orders were rejected (minimum notional); reconciliation (cash + positions = equity) holds; two replays are bit-identical (F13).

## 4. Predictions that were wrong (reported, not corrected)
F01 (predicted single-event loss ≤ 0.152, observed 0.162 — realized exposure 0.167 at the event, see 3.1), F02 (predicted shutdown, observed none — see 3.5), F03 LV-2 (predicted none, observed `tier3_floor`), F06 LV-2 (predicted no transition, observed tier 1), F08 as run (predicted shutdown; the declared event did not occur, §6). Frozen predictions were not edited.

## 5. Causality and estimator tests (`tests/test_m6_s0_sizing.py`)
Annualisation (daily σ × √365) against an independent computation; prefix invariance (mutating all candles at or after the decision time leaves σ̂ unchanged); zero volatility → exposure = cap, no division; missing close or < 60 days of history → σ̂ NaN → exposure 0; deterministic replay equals the stored row; cash + liquidation value of positions = equity (rel. 1e-9); V3 configuration unchanged (tier 3 = 18 %, tier 2 = 15 %, recovery 0).

## 6. Test-harness defect correction (declared)
F08 did not exercise its declared event (a held asset stale > 48 h): the fail-closed estimator liquidated the sleeve after the 12 h hole in another asset, so no position was held later (equity constant 1004.2, zero impaired ticks). Per the freeze rule the fixture was replaced by F08a (12 h hole) and F08b (60 h hole starting right after a Monday resize), predictions and acceptance rules unchanged, recorded in `protocol/m6_s0_defect_corrections.json`; the first-run F08 row is kept and used as evidence for nothing; the other 12 fixtures' rows are byte-identical to the first run.

## 7. Overlap audit (existing documents + synthetic fixtures only)
| Dimension | Family A V0 (`family_a.py`, evaluated: not credible) | S7 C2 (design, never registered) | H1 MAX3 (L1 PASS, L2 NO-GO) | M4 low-volatility comparator | Proposed `lv_sleeve` |
|---|---|---|---|---|---|
| Selection | none (8 fixed pairs) | lowest-volatility tercile, 60 d, PIT universe | −MAX3 quintile, 28 d (rank correlation −0.913 with 28 d volatility) | lowest 28 d volatility, quintile, same K | lowest 60 d volatility tercile, PIT universe |
| Weighting | 1/N × min(1, 40 %/σ_i30) per asset | equal | equal notional | equal notional | equal (liquidity-capped) |
| Exposure | per-asset inverse volatility, up to fully invested | "60–100 % of wallet when allowed" (assumption) | ~100 % invested | ~100 % invested | ≤ 15 % sleeve; LV-1 `min(0.15, 10 %/σ̂_basket)` |
| Timing | daily, rebalance band 5 pp | monthly | 7 / 28 days | 7 / 28 days | monthly selection, weekly resize |
| Execution | Stage 0 engine, base/stress costs | not specified | hourly engine, 1 h latency, participation cap 10 % | same | same as M4 |
| Risk | terminal breaker (20 %); halted after 8.7 % of the period | V3 problem noted (NO-GO) | V3: SHUTDOWN 2021-02-23 / 2021-05-19 | V3: shut down | V3 unchanged; shutdown **not** excluded (§3) |
Synthetic check (test `test_overlap_exposure_rule_equivalence_with_family_a_v0`): above basket volatility 66.7 % the LV-1 exposure equals **exactly 0.25 × the Family A V0 exposure** (`min(1, 0.4/σ)`); both are non-increasing in volatility with the same ordering. The cap and the scale factor are the only exposure-rule differences.
**Assessment:** (i) the *return hypothesis* — lower-volatility assets are preferable — is the same as S7 C2 and the M4 low-volatility comparator, and is the volatility confound found in H1; (ii) the *exposure rule* is Family A V0's inverse-volatility scaling, scaled by 0.25 and capped lower; (iii) the genuinely new elements (portfolio-level target, 15 % cap, split of selection and allocation tests) are a **risk overlay**, not a new return hypothesis, and the overlay's headline property (no shutdown) is falsified (§2). The selection evidence on the development window is exploratory (the association was seen in H1) and is **not** independent evidence.

## 8. Limitations
Synthetic shapes chosen from the owner's list, not calibrated to markets; one seed per fixture; 1,000 USDT wallet (minimum notional matters; 10,000 not tested); fixed 10-asset basket (no selection, no PIT churn, no delisting probabilities); per-fixture single event structure; no L1a inference calibration (unresolved, M5 not reopened: the binomial-rule lesson stands); commercial data licensing unresolved; no market statistic was computed.

## 9. Recommendation (not an authorisation)
**NO-GO for registration of `lv_sleeve` (S1 and later).** Reasons: the overlap audit finds only a risk overlay on previously evaluated or specified components (no distinct return hypothesis); the central safety claim is falsified (cumulative loss, drift, integrity shutdowns); the realistic behaviour after the first tier-2 event is a near-permanent cash state; L1a would be non-independent and statistically unable to demonstrate profitability. No further research round is recommended under the current budget; if the owner still wants an operational, no-alpha-claim risk-capped sleeve for paper trading, that needs a different framing (V3 handling of delistings, resize policy, account size) and a separate approval.

## 10. CI note (added after the first CI run of the harness)
The upstream macOS-26 / Python 3.14 job failed on `89cbbd1` in `test_determinism_and_reconciliation_on_a_stored_fixture`: the replayed F06 row matched the stored row in all 23 behavioural fields but `order_hash` and `equity_series_hash` differ (floating-point hashes are platform specific). This was a defect of the test (cross-platform hash equality), not an infrastructure problem and not a research result; the test now compares behavioural fields with a 1e-9 tolerance across platforms and hashes only within one platform. Stored hashes in `m6_s0_results.json` are Linux values. Fixture outcomes, predictions and acceptance rules are unchanged.
