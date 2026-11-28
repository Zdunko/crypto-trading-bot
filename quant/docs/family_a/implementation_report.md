# Family A - implementation report and proposed evaluation protocol (NO market evaluation has been run)

Authorised 2026-11-25: finalise the specification and implement the architecture with synthetic tests and causality validation.
Not authorised yet: any market evaluation, paper trading, live trading, holdout use.

## Decisions applied
1. Circuit breaker is ON in every evaluation; its impact is reported separately (events from the ON run).
2. Halt: no new entries; pending entry orders cancelled; all positions liquidated at the next executable price with fees,
   slippage and a volume participation cap (10 % of a candle's volume; the remainder continues each following candle and never
   expires); no automatic restart inside an evaluation run (terminal). Only an owner approval timestamp could resume (not used).
3. Implementation and market evaluation need separate approvals.

## What exists
- `quantlab/family_a.py` - strategy (`FamilyAStrategy`), variants A1 / A0 / V0, `episodes()` (T1 trade definition),
  `run_family_a()` (candles before the start are warm-up history only).
- `protocol/protocol_v5_family_a.json` - frozen specification and evaluation rules; `frozen_manifest_v5.json` pins it with the engine.
- Engine amendments (additive, default-off, Stage 0 tests unchanged; manifest v4 regenerated before any market result):
  add-to-position buys with weighted cost basis, `max_participation` liquidity cap, halt liquidations never expire,
  volume carried in `PriceData`.
- Tests: `tests/test_family_a.py` (18) + 1 freeze test. Local gate: 318 passed. Synthetic data only.
  Covered: daily aggregation from completed days, filter scoring with fail-closed warm-up, volatility arithmetic, weight cap
  (sum of weights <= 1 on 500 random draws), midnight-only decisions, uptrend/downtrend behaviour, rebalance band, partial sells
  and cost-basis reconciliation, halt (cancel, liquidate with costs, no restart), halt never expiring across missing candles,
  liquidity-capped liquidation over several candles, mutation causality at three cut points for A1 and V0, restart causality,
  determinism, code defaults == frozen JSON.

## Specification (frozen, unchanged from the approved proposal)
Daily decision at 00:00 UTC from completed days; score = share of close > SMA(50/100/200) (missing history = not satisfied);
sigma = 30-day annualised volatility; target = (1/N) * score * min(1, 40 % / sigma) * breaker multiplier; rebalance only if the weight
moves > 5 percentage points (or target is zero). Costs 0.10 % + 0.05 % per side (stress 2x). No leverage, no shorting, cash earns 0 %.

## Proposed evaluation protocol (needs your approval; one CI run, evaluation period 2021-01-01..2025-07-01 only)
1. Run A1, A0, V0 once each (base costs, breaker ON) plus the 2x-cost stress for A1; no parameter changes after seeing results.
2. Report per variant: net and annualised return, max drawdown, Sharpe, Sortino, profit factor, exposure (average/peak), turnover,
   monthly returns, pair concentration, regime table, T1-T10 verdict (T1 = position episodes; T9 not evaluated), benchmarks B1-B5.
3. Breaker impact (separate section): time and equity at halt, drawdown, share of the period traded, days flat afterwards,
   liquidation cost, entries blocked. No breaker-OFF run unless you approve it separately (it would be diagnostic only).
4. Statistics: Holm over H1/H2, N = 43, deflated Sharpe, 95 % block bootstrap, underpowered rule (detectable Sharpe ~1.17 at 1642 days),
   V0 vs B1 never counted as alpha.
5. Verdict wording fixed in advance: "passes statistical screen", "not credible" or "underpowered" - never "validated".
6. Holdout untouched; a single use per finalist only after separate written approval.

## Remaining risks (stated before any result)
- A terminal halt can truncate the run (R1 lost most of its period this way); the report must show the traded share of the period.
- T4 (drawdown <= 20 %) and T5 (PF >= 1.3) are demanding; T1 (>= 200 episodes) may be unreachable with 8 assets; sample is underpowered
  below Sharpe ~1.2. None of these are softened.
- Survivor-biased 8-pair universe; research data is not out-of-sample; costs and the participation cap are assumptions.
- Hourly candles: intrabar order unknown; the daily rule uses 00:00 opens, so decisions are not tied to a specific exchange fill.
- Real-data behaviour of the strategy (e.g. listing gaps of young pairs: SOL/ADA/LINK/DOGE start 2020-09/10) is untested until the
  evaluation; pairs without enough history get weight 0 by construction.
- SMA(200) needs 200 completed days; the evaluation starts 2021-01-01 with only ~90 days of history for the youngest pairs, so their
  full score is unavailable until about April 2021 (fail-closed, disclosed, not tuned).
