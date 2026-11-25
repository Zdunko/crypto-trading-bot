# Phase 3 validation thresholds — PROPOSAL for owner approval

Fixed **before** any backtest result exists. The numbers are priors chosen for conservatism,
**not derived from data**; if the owner changes them, change them now, not after seeing results.
Once approved, editing a threshold or a strategy rule after looking at out-of-sample (OOS)
results invalidates that OOS period (a fresh hold-out is then required).

## Protocol
- Universe: the 8 pairs in `configs/base.json`, 1h candles, exchange chosen after the network probe.
  **Survivorship caveat:** the pairs were chosen today, with hindsight; delisted coins are absent.
  Results are therefore optimistic by an unknown amount and are reported with this caveat.
- Split: development period = start of data → 2022-12-31 (sanity, cost stress, regime table);
  **OOS = 2023-01-01 → latest data, evaluated once per strategy, after the rules are frozen.**
- Walk-forward: parameters are fixed, so no refitting; instead rolling 6-month test windows
  (non-overlapping) measure stability across time. If parameter selection is ever introduced, it
  uses anchored windows (≥ 12 months train, 3 months test) and is a separate, new proposal.
- Costs: 0.15 % per side baseline; stress at 0.30 % per side.
- Benchmark: equal-weight buy-and-hold of the same pairs over the same period, same costs.
- Multiple testing: 4 strategies are evaluated; every extra variant tried is logged in the journal
  and counted. Passing requires **all** thresholds below.

## A strategy is "validated" only if, on aggregated OOS results
| # | Criterion | Threshold |
|---|---|---|
| T1 | Sample size | ≥ 100 closed trades, and no single pair contributes > 30 % of net profit |
| T2 | Net return after costs | > 0 |
| T3 | Risk-adjusted vs benchmark | Sortino ≥ benchmark Sortino |
| T4 | Drawdown | max drawdown ≤ 30 % **and** ≤ benchmark max drawdown |
| T5 | Profit factor | ≥ 1.2 |
| T6 | Cost stress (0.30 % per side) | net return > 0 and profit factor ≥ 1.0 |
| T7 | Walk-forward stability | ≥ 60 % of 6-month windows with positive net return; no window > 50 % of total profit |
| T8 | Regimes (bull / bear / sideways on BTC/USDT) | profit factor ≥ 0.8 in every regime that has ≥ 30 trades; report all three |
| T9 | Parameter robustness | with each parameter moved across its allowed range (one at a time), net return > 0 in ≥ 75 % of variants |
| T10 | Bias | `lookahead-analysis` and `recursive-analysis` clean (Phase 2 D4) |

Reported for every strategy (no threshold): net return, max drawdown, Sharpe, Sortino, profit
factor, win rate, expectancy, number of trades, monthly performance table, exposure time.

## What happens on failure
A failing strategy is **rejected and documented** (journal entry with the failing criteria). It
is not re-tuned until it passes. "No strategy validated" is an acceptable, honest Phase 3 outcome.
