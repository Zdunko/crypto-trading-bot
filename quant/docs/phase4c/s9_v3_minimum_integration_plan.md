# S9 — Risk Management V3: minimum integration plan (G1, G3, G5; G2 as policy)

Plan only: no code in S9, V3 is not adopted into any evaluation, `risk_v2.py` and `risk_v3.py` stay byte-unchanged. Scope is deliberately limited to the three evidence gaps from `s8_risk_v3_adoption_review.md`; no new infrastructure.

## Policy for G2 (decided, no test needed beyond the existing ones)
- **Zero recovery is the primary assumption** for delisted, suspended, untradeable or missing assets (`gate_recovery = 0.0`, already the V3 default and frozen in `risk_v3_spec.json`).
- Every report that uses V3 includes the existing five-point sensitivity (0, 0.25, 0.5, 0.75, 1.0) next to the primary result; the primary result is never replaced by a sensitivity row.
- **An assumed recovery value is a valuation input, never executable liquidity.** Proceeds exist only from fills that the engine actually executed; a position in an impaired asset is never assumed sold at any recovery value.

## Tests required before any evaluation may use V3
| Gap | Test (written first, pytest, synthetic only) | Pass condition | Effort |
|---|---|---|---|
| G1 engine integration | V3-wrapped strategy inside `quantlab/execution.py` on a seeded synthetic 40-asset, 4.5-year feed with injected delistings, multi-day gaps and halts; the same feed without defects is run under V2 and V3 | clean-subset results are **identical** to V2 (equity curve and fills); with defects the equity uses zero recovery, no order is created for an impaired asset, and fees/min-notional/participation behave as in the engine | about 1 session, ~150 lines of test plus a small feed builder |
| G3 status source | statuses derived **only** from the point-in-time epoch table and observed candle gaps; prefix-invariance test: statuses computed on a feed truncated at date t equal the statuses of the full feed at every date <= t | identical for every t on 3 seeded feeds; a mutation that reads a future epoch makes the test fail | about 0.5 session |
| G5 resume after a gap | an asset resumes after 47 h (no alarm) and after 49 h (alarm, SHUTDOWN permanent), each with +60 % and -60 % first-print gap move | no alarm at 47 h; alarm at 49 h and permanent; capital-protection report shows the jump instead of hiding it; gross exposure and drawdown follow the zero-recovery valuation | about 0.5 session |

Total: about 2 sessions. If any test fails the defect is fixed in a new versioned V3 file (3.0.1), never by editing frozen files.

## Not included (avoid unrelated expansion)
sub-hourly monitoring, new data feeds, a status feed from an exchange, any change of the 48 h horizon, 20 % limit or tier thresholds.
