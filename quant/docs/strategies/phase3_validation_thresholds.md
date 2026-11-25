# Phase 3 validation protocol — v2 (FROZEN)

Machine-readable twin: `quant/protocol/protocol.json`. Integrity: `quant/protocol/frozen_manifest.json`
(sha256 of this protocol, every strategy, `quant_common.py` and every config). CI and every research
stage fail if any of them changes after the freeze. A change needs a new protocol version and the
owner's approval; **results seen so far never justify a change**.

Owner decision, 2026-11-25: Phase 2 conditionally approved; OKX approved as the data source; T1, T4, T5
tightened; remaining thresholds unchanged; fees and slippage explicit and never double-counted; an
untouched holdout; broader bias checks; uncertainty, sample limits and survivorship bias reported;
no optimisation on holdout results.

## What changed from v1

| Item | v1 (proposal) | v2 (frozen) |
|---|---|---|
| T1 sample size | ≥ 100 closed trades | **≥ 200 closed trades** (pair-share limit 30 % unchanged) |
| T4 drawdown | ≤ 30 % and ≤ benchmark | **≤ 20 % and ≤ benchmark** |
| T5 profit factor | ≥ 1.2 | **≥ 1.3** |
| T2, T3, T6, T7, T8, T9, T10 | — | unchanged (T6 stress is still 0.30 % per side) |
| Costs | one lumped 0.15 % `fee` | **fee and slippage separate** (below) |
| Out-of-sample | one period 2023 → | evaluation 2021-01 → 2025-07 **plus an untouched holdout** 2025-07 → 2026-11 |
| Bias checks | 3 pairs, 1 year | **8 pairs × 6 half-year periods** inside the evaluation period, recursive on 3 pairs × 6 periods |

## Data
OKX spot, 1h candles, 8 pairs (BTC, ETH, SOL, XRP, ADA, LINK, LTC, DOGE vs USDT), window
2020-01-01 → 2026-11-25 (exclusive), public API, no credentials. Validation (run 45558871512): **0 missing
candles, 0 gaps, 0 duplicates, 0 impossible candles in all 8 pairs**; SOL lists 2020-09-30, the others
2020-01-01; one warning (DOGE: 1 hourly move above 50 %). Dataset sha256
`fd94dcb657341422cb7109377585418d70cc25b5ed2f538454034b3e7bb58085`; every stage downloads again and aborts if
the hash differs.

## Periods (fixed from data availability and calendar boundaries before any return was computed)
- **Evaluation:** 2021-01-01 → 2025-07-01. Used for backtests, cost stress, 9 walk-forward windows of 6 months,
  regimes, parameter robustness and bias checks. The final verdict T1–T10 is made here.
- **Holdout:** 2025-07-01 → 2026-11-25. **Not loaded by the evaluation stage** (it only reads the evaluation
  range), not used for bias checks, not used for parameter ranges. Evaluated once, only for strategies that
  passed T1–T10, with files identical to the frozen manifest. Holdout criteria: H1 net return > 0, H2 max
  drawdown ≤ 20 %, H3 profit factor ≥ 1.0 (base costs). A strategy is "validated" only if it also passes the
  holdout; a holdout failure is reported and never answered with a rule change.
- If no strategy passes T1–T10, **the holdout is never evaluated** and stays untouched.

## Costs: fee and slippage, each counted exactly once
| | Fee per side (Freqtrade `--fee`) | Slippage per side (applied afterwards to fills) | Extra slippage on stop-loss exits | Total per side |
|---|---|---|---|---|
| Base | 0.10 % | 0.05 % | +0.05 % | 0.15 % (stop exits 0.20 %) |
| Stress (T6) | 0.20 % | 0.10 % | +0.10 % | 0.30 % (stop exits 0.40 %) |

- The fee is the only thing Freqtrade charges; slippage is added by `quantlab.costs.apply_costs`, which
  **refuses trades whose recorded fee differs from the scenario fee** (a lumped fee cannot be stacked on top;
  tested, and `configs/backtest.json` must equal the protocol fee).
- Profit is recomputed from amount, rates and fees; Freqtrade's own `profit_abs` is not trusted.
- Equity is marked to market hourly at liquidation value (close less exit fee and slippage), and the
  benchmark pays the same costs once at entry and once at the end.
- **Assumptions, not measurements:** 0.10 % taker fee for a regular OKX tier; flat slippage because orders are
  tiny relative to 1h volume of these pairs; slippage is not fed back into Freqtrade's position sizing
  (second-order); fills at candle open and stops at the stop price are optimistic. The stress scenario and the
  limitations section exist for this reason.

## Benchmark
Equal-weight buy-and-hold of the pairs already listed at the period start, never rebalanced, same costs,
liquidation value. BTC-only buy-and-hold is reported for reference, and Freqtrade's own `BuyAndHold` strategy
(limited to 3 slots) is run for completeness. T3 and T4 compare against the equal-weight benchmark.

## Criteria on the evaluation period (all must hold)
| # | Criterion | Threshold |
|---|---|---|
| T1 | Sample size | ≥ 200 closed trades; no single pair > 30 % of net profit |
| T2 | Net return after base costs | > 0 |
| T3 | Sortino vs benchmark | ≥ benchmark Sortino |
| T4 | Max drawdown (hourly mark-to-market) | ≤ 20 % **and** ≤ benchmark |
| T5 | Profit factor | ≥ 1.3 |
| T6 | Stress costs | net return > 0 and PF ≥ 1.0 |
| T7 | Walk-forward (nine 6-month windows, parameters fixed) | ≥ 60 % of windows positive; no window > 50 % of total profit |
| T8 | Regimes (BTC/USDT daily ADX/EMA200; trade assigned the regime of the last completed day) | PF ≥ 0.8 in every regime with ≥ 30 trades |
| T9 | Parameter robustness (22 one-at-a-time variants at the ends of the allowed ranges) | ≥ 75 % of variants with net return > 0 |
| T10 | Bias | lookahead: no bias in any of 6 periods and evaluated in ≥ 3; recursive variance ≤ 0.1 % at the strategy's own startup column for 3 pairs × 6 periods |

Undefined values (NaN) never pass.

## Uncertainty, sample limits, survivorship (reported for every strategy)
- 95 % intervals for net return, Sortino, Sharpe, Sortino/return difference vs benchmark (circular block
  bootstrap, 10-day blocks, 2000 resamples, fixed seed) and for profit factor and expectancy (trade-level
  bootstrap). Intervals are **optimistic**: they assume the sample is representative and trades overlap.
- Sample limits: about 4.5 years and one market cycle; crypto pairs are strongly correlated, so 200 trades are
  far fewer than 200 independent observations; windows and regimes can hold few trades.
- **Survivorship bias:** the 8 pairs were picked in 2026 and all still trade on OKX; coins that were delisted or
  collapsed are absent, which inflates buy-and-hold and any long-only strategy by an unknown amount.
- Multiple testing: 4 strategies × several criteria; a pass can be luck. All 22 + 4 backtests are reported.

## Process rules
1. No strategy rule, parameter, config, threshold or period changes after the freeze (manifest enforces it).
2. Every research run (id, commit, purpose) is logged in the journal, including reruns after bugs; analysis
   code fixes are allowed and logged, strategy/threshold changes are not.
3. The holdout is never used to choose, tune or reject-and-retry anything. A failed strategy is rejected.
4. "No strategy validated" is an acceptable and honest outcome.
