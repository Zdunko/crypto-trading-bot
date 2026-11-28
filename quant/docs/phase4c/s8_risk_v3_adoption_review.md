# S8 — Risk Management V3: adoption readiness review

Status: **review only. V3 is NOT adopted into any market evaluation.** `risk_v3.py`, `risk_v2.py` and every frozen artifact are unchanged.

## What is established (synthetic fixtures, S7)
- 51 unit/invariant tests: elapsed-time stale alarm equals the V2 hourly alarm, a 4-hour monitor interval alarms at 48 elapsed hours, cadence other than hourly is refused, daily strategy decisions run with hourly risk ticks, explicit statuses, closed-form conservative valuation at recovery 0 / 0.5 / 1, monotone sensitivity, concealed-drawdown detection, V3 ≡ V2 equivalence on 6 seeds, cross-process determinism, 30 seeded invariant scenarios.
- The S2 thresholds (tiers 10/15/18 %, hard limit 25 %, 20 % T4 limit) are untouched.

## What is NOT established (reasons for not adopting yet)
| # | Gap | Why it matters | Required before adoption |
|---|---|---|---|
| G1 | Never run through the full Stage 0 engine on a real multi-asset schedule | the equivalence tests use small synthetic feeds; interaction with partial fills, min notional and the participation cap is untested at scale | integration test: V3 wrapper inside `execution.py` on a synthetic 40-asset, 4.5-year feed with injected delistings, gaps and halts; compare with V2 on the clean subset (must be identical) |
| G2 | Recovery assumption (default 0 for gate valuation) is a policy choice, not a measured fact | conservative for capital protection, but it also shuts paths down early; effect on the invested share is already costly (S7 q6: share 0.32-0.65) | owner decision on the gate recovery fraction, documented as an assumption; sensitivity table kept in every report |
| G3 | Delisting write-off timing is assumed from the status feed | PIT dataset epochs give listing/delisting dates, but the feed that marks SUSPENDED/UNTRADEABLE does not exist in the PIT dataset | define the status source (dataset epoch table only), test that no status is derived from future information |
| G4 | The 58-68 % synthetic shutdown rate and the low invested share make absolute-return claims hard | not a V3 defect: it is the frozen S2 design plus the 20 % limit; but it feeds the power problem (see S8 report) | do not change thresholds; keep V3 neutral on exposure |
| G5 | No test against a partially recovered asset (price jump after a long gap) | stale valuation could hide an upward as well as a downward jump | add a fixture: asset resumes after 47 h (no alarm) and after 49 h (alarm, permanent) with a 60 % gap move |
| G6 | Monitoring cadence is fixed at 1 hour; sub-hourly data is not used | intrahour gap-down not seen | accepted limitation, documented (L-STALEPOS-V3) |
| G7 | Versioned adoption rule is missing | adoption must be a new pre-registered file and freeze record, not an edit | S9 proposal if the owner wants V3 used |

## Verdict
**NOT READY for formal adoption. CONDITIONAL on G1, G3 and G5 (tests) and on an owner decision for G2.** The design itself shows no known defect on synthetic fixtures; the missing items are integration evidence and one policy decision. Adoption would change the evaluated behaviour of every future strategy, so it must not happen implicitly inside a market evaluation.

## Remaining assumptions (kept explicit)
1. Liquidation is never assumed; positions in impaired assets stay on the books at the conservative value.
2. The conservative recovery used for gating is 0 by default; reporting uses the five-point sensitivity.
3. The 48-hour horizon is inherited from S2 and not re-optimised.
4. Statuses are exogenous inputs; V3 does not infer delisting.
