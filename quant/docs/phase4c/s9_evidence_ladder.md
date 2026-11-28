# S9 — Evidence Ladder (separate prospective protocol)

Machine-readable definition: `protocol/evidence_ladder_v1.json`. It is a **proposal that takes effect only for a family the owner registers**. It does not modify T1-T10, any manifest or any acceptance record, and it does not reclassify any rejected strategy.

| Level | Question | Statistic | Passing means | Passing does NOT mean |
|---|---|---|---|---|
| L1 | a pre-registered point-in-time signal ranks next-period returns across liquid spot assets | mean daily cross-sectional IC, HAC (lag fixed ex ante), Holm over the family | a predictive relationship is unlikely to be chance | profit, costs, capacity, risk limits, T1-T10 |
| L2 | a long-only spot portfolio built from the signal beats comparators **net of realistic costs** | paired net active return vs cash, BTC, PIT equal weight, exposure-matched; 1x and 2x costs; V3 risk layer, zero recovery | the signal is economically viable on history | robustness, operations |
| L3 | the result survives disjoint sub-universes, periods and regimes fixed ex ante | sign and size per slice | not driven by one slice | forward evidence (history is shared) |
| L4 | forward paper trading is reliable and tracks the engine | reconciliation, tracking error, incident log | operational readiness | profitability (forward time accrues one year per year) |
| L5 | controlled live deployment | not defined | nothing | **unreachable without a separate written owner approval** |

Rules: levels are passed in order and reported as exactly the level passed; a statement implying a higher level is a defect; a signal passing L1-L3 is not a strategy validated under T1-T10; the holdout stays untouched until a separate owner decision after L3.

## Three kinds of significance, never merged
1. **Statistical** (L1): HAC or block-bootstrap inference, Holm across every pre-registered configuration and horizon.
2. **Economic** (L2): net of fees, slippage and 2x stress, against comparators, with the break-even cost reported.
3. **Tradability** (L2/L4): capacity, minimum notional, participation cap, V3 risk limits, data licence.

## Research budget accounting (N = 43/52 preserved)
- No market experiment exists before the family is registered with owner approval. S9 adds nothing to N.
- The recommended hypothesis is **one family**: it consumes one of the 3 remaining family slots and at most 3 configurations (N 43 -> at most 46). Non-selected hypotheses are not tested and cost nothing.
- Re-running an identical registered configuration adds nothing; any changed definition, window, horizon, universe threshold or parameter is a new configuration and is charged.
- **No exploratory experiments.** Computing any market-derived statistic of a candidate signal before pre-registration counts as an experiment and is forbidden.

## Protection against researcher degrees of freedom
One universe rule, one formula and one fixed scalar per configuration; evaluation window, sub-periods, regimes, comparators, lags and stop rule fixed in writing before any market data of the signal is read; nothing dropped or added after results; a registered stop rule: a hypothesis not rejected at L1 terminates, with no variant search. A disguise check (rank correlation with rejected-family signals, threshold 0.7) is part of L1.
