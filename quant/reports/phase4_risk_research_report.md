# Phase 4 - R1 risk-overlay research report (research data, diagnostics only)

Source: Quant research run 45653877385, commit 20b972b (protocol v3 + errata). Run 1 (commit 1e99407, run 45644306073)
is INVALID (overlay equity double counted realised profit, see `protocol_v3.json` errata) and is not used.

Protocol v3; period 2021-01-01 -> 2025-07-01 (holdout untouched); backtests run: 14.

NOT validation: all data here is research data. No configuration was selected or tuned on these results.

## Benchmark set (T3 = highest Sortino, T4 = lowest drawdown, 20 % binding)

| benchmark | net | max DD | Sharpe | Sortino |
|---|---|---|---|---|
| B1 equal-weight all 8 | 1896.5 % | 89.7 % | 1.16 | 1.81 |
| B2 equal-weight ex-SOL | 721.3 % | 90.9 % | 0.95 | 1.57 |
| B3 BTC+ETH | 253.0 % | 79.4 % | 0.75 | 1.09 |
| B4 BTC | 269.4 % | 77.2 % | 0.78 | 1.16 |
| B5 equal-weight monthly rebalanced | 1660.4 % | 81.6 % | 1.17 | 1.78 |

Thresholds used: Sortino >= 1.81, drawdown <= min(20 %, 77.2 %).

## Bias checks (lookahead + recursive, R1 strategies)

- TrendEmaCrossR1: clean=False; lookahead evaluated 4, biased 2; recursive checks 18, failed 0
- MomentumRocR1: clean=False; lookahead evaluated 4, biased 2; recursive checks 18, failed 0

### TrendEmaCross: R0 (no overlay) vs R1 (overlay)

| metric (base costs unless stated) | R0 | R1 |
|---|---|---|
| net return | 583.3 % | -19.0 % |
| annualised return | 53.3 % | -4.6 % |
| max drawdown (MTM, hourly) | 72.2 % | 21.8 % |
| Sharpe | 1.02 | -0.58 |
| Sortino | 1.67 | -1.08 |
| profit factor | 1.18 | 0.83 |
| trades | 830 | 833 |
| win rate | 25.4 % | 29.5 % |
| time in market | 75.4 % | 27.7 % |
| avg open positions | 1.83 | 0.47 |
| avg / peak gross exposure | n/a | 4.9 % / 59.7 % |
| stress net return (fee 0.2 % + slippage 0.1 %) | 207.9 % | -45.8 % |
| stress profit factor | 1.09 | 0.64 |
| monthly returns | 25/54 positive; best 152.4 %, worst -22.4 % | 15/54 positive; best 7.6 %, worst -3.3 % |
| max pair share of profit | 63.1 % | n/a |

Regimes (profit factor / trades):

| regime | R0 | R1 |
|---|---|---|
| bull | 1.00 / 282 | 0.78 / 395 |
| bear | 0.75 / 193 | 6.07 / 5 |
| sideways | 1.60 / 355 | 0.84 / 433 |

R1 window returns (nine 6-month windows):

| 2021-01 | 2021-07 | 2022-01 | 2022-07 | 2023-01 | 2023-07 | 2024-01 | 2024-07 | 2025-01 |
|---|---|---|---|---|---|---|---|---|
| -5.2 % | 2.4 % | -2.6 % | -5.9 % | -4.1 % | 2.1 % | -4.3 % | -3.0 % | 0.2 % |

R1 criteria vs thresholds (diagnostic, T3 = 1.81 Sortino, T4 benchmark drawdown = 77.2 %):

| id | criterion | value | threshold | passed |
|---|---|---|---|---|
| T1a |  | 833.000 | >= 200 | yes |
| T1b |  | None | <= 0.3 | NO |
| T2 |  | -0.190 | > 0 | NO |
| T3 |  | -1.080 | >= 1.806 | NO |
| T4 |  | 0.218 | <= 0.200 (min of 0.2, benchmark) | NO |
| T5 |  | 0.827 | >= 1.3 | NO |
| T6 |  | [-0.4579020282385853, 0.6442050865275583] | > 0 and >= 1.0 | NO |
| T7a |  | 0.333 | >= 0.6 | NO |
| T7b |  | n/a | <= 0.5 | NO |
| T8 |  | {'bull': 0.7761885887517929} | >= 0.8 where trades >= 30 | NO |
| T9 |  | None | >= 0.75 | not evaluated |
| T10 |  | False | True | NO |

Circuit-breaker halts in R1: 0 

Entry decisions in R1: accepted 833, denied {'cluster_pause': 106, 'pair_cooldown': 46, 'corr': 174, 'regime_bear': 380}

Ablations (descriptive only; not used to select anything):

| configuration | net | max DD | Sortino | PF | trades | time in market | stress net | halts |
|---|---|---|---|---|---|---|---|---|
| R1 (all components) | -19.0 % | 21.8 % | -1.08 | 0.83 | 833 | 27.7 % | -45.8 % | 0 |
| no_vol_sizing | -8.4 % | 21.5 % | -0.36 | 0.73 | 38 | 1.2 % | -11.4 % | 1 |
| no_exposure_limits | -19.0 % | 21.8 % | -1.08 | 0.83 | 833 | 27.7 % | -45.8 % | 0 |
| no_correlation | -25.3 % | 27.5 % | -1.78 | 0.72 | 873 | 27.3 % | -46.5 % | 0 |
| no_regime_filter | -21.9 % | 24.4 % | -1.51 | 0.69 | 407 | 12.6 % | -34.6 % | 1 |
| no_stop_cooldown | 67.1 % | 9.1 % | 2.72 | 1.84 | 632 | 62.7 % | 57.3 % | 0 |
| no_circuit_breaker | -19.0 % | 21.8 % | -1.08 | 0.83 | 833 | 27.7 % | -45.8 % | 0 |

### MomentumRoc: R0 (no overlay) vs R1 (overlay)

| metric (base costs unless stated) | R0 | R1 |
|---|---|---|
| net return | 1074.0 % | -14.8 % |
| annualised return | 72.9 % | -3.5 % |
| max drawdown (MTM, hourly) | 75.5 % | 23.1 % |
| Sharpe | 1.11 | -0.50 |
| Sortino | 1.97 | -0.72 |
| profit factor | 1.22 | 0.85 |
| trades | 523 | 699 |
| win rate | 30.0 % | 33.0 % |
| time in market | 70.7 % | 18.7 % |
| avg open positions | 1.75 | 0.40 |
| avg / peak gross exposure | n/a | 2.5 % / 46.9 % |
| stress net return (fee 0.2 % + slippage 0.1 %) | 610.5 % | -30.4 % |
| stress profit factor | 1.15 | 0.72 |
| monthly returns | 25/54 positive; best 139.8 %, worst -33.9 % | 8/54 positive; best 3.0 %, worst -4.0 % |
| max pair share of profit | 84.6 % | n/a |

Regimes (profit factor / trades):

| regime | R0 | R1 |
|---|---|---|
| bull | 1.34 / 197 | 0.72 / 333 |
| bear | 0.45 / 110 | n/a / 0 |
| sideways | 1.46 / 216 | 1.12 / 366 |

R1 window returns (nine 6-month windows):

| 2021-01 | 2021-07 | 2022-01 | 2022-07 | 2023-01 | 2023-07 | 2024-01 | 2024-07 | 2025-01 |
|---|---|---|---|---|---|---|---|---|
| 0.3 % | -4.9 % | -2.9 % | -3.3 % | -4.9 % | 0.0 % | 0.0 % | 0.0 % | 0.0 % |

R1 criteria vs thresholds (diagnostic, T3 = 1.81 Sortino, T4 benchmark drawdown = 77.2 %):

| id | criterion | value | threshold | passed |
|---|---|---|---|---|
| T1a |  | 699.000 | >= 200 | yes |
| T1b |  | None | <= 0.3 | NO |
| T2 |  | -0.148 | > 0 | NO |
| T3 |  | -0.721 | >= 1.806 | NO |
| T4 |  | 0.231 | <= 0.200 (min of 0.2, benchmark) | NO |
| T5 |  | 0.849 | >= 1.3 | NO |
| T6 |  | [-0.30429416315548274, 0.7209866709531805] | > 0 and >= 1.0 | NO |
| T7a |  | 0.111 | >= 0.6 | NO |
| T7b |  | n/a | <= 0.5 | NO |
| T8 |  | {'bull': 0.7244339333234971} | >= 0.8 where trades >= 30 | NO |
| T9 |  | None | >= 0.75 | not evaluated |
| T10 |  | False | True | NO |

Circuit-breaker halts in R1: 1 [{'type': 'halt', 't': '2023-03-20 04:00:00+00:00', 'dd': 0.20120232147605, 'equity': 912.1102482, 'id': 'halt-20230320T0400'}]

Entry decisions in R1: accepted 699, denied {'cluster_pause': 6012, 'pair_cooldown': 7997, 'corr': 994, 'regime_bear': 8391, 'halted': 44363}

Ablations (descriptive only; not used to select anything):

| configuration | net | max DD | Sortino | PF | trades | time in market | stress net | halts |
|---|---|---|---|---|---|---|---|---|
| R1 (all components) | -14.8 % | 23.1 % | -0.72 | 0.85 | 699 | 18.7 % | -30.4 % | 1 |
| no_vol_sizing | 5.0 % | 21.2 % | 0.30 | 1.18 | 31 | 0.8 % | 2.5 % | 1 |
| no_exposure_limits | -14.8 % | 23.1 % | -0.72 | 0.85 | 699 | 18.7 % | -30.4 % | 1 |
| no_correlation | -16.8 % | 24.6 % | -0.82 | 0.82 | 699 | 18.3 % | -31.8 % | 1 |
| no_regime_filter | -7.0 % | 22.9 % | -0.23 | 0.94 | 575 | 15.2 % | -25.2 % | 1 |
| no_stop_cooldown | 99.6 % | 19.1 % | 2.56 | 2.05 | 422 | 62.5 % | 91.3 % | 0 |
| no_circuit_breaker | -46.2 % | 51.5 % | -1.72 | 0.78 | 1538 | 41.9 % | -86.6 % | 0 |

## Reading notes (written after the numbers, nothing here changes a rule or parameter)

- Every R1 variant fails T2-T8 and T10 on research data; T9 was not evaluated (frozen parameters). Nothing is validated.
- R1 does reduce the drawdown versus R0 (21.8 % / 23.1 % versus 72.2 % / 75.5 %) but it also loses money after costs, and the
  drawdown is above the binding 20 % limit (T4 fails). The circuit breaker saw only Freqtrade fee-only equity, so a
  drawdown passed 20 % without a halt (hourly MTM 21.8 % / 23.1 %); see quant/docs/phase4b for the corrected explanation (the breaker also ran in custom_stoploss, but saw a cheaper cost world); MomentumRoc halted once (2023-03-20), after which
  it never traded again (backtest halts are terminal by design: no owner approval is possible in a backtest).
- `no_stop_cooldown` switches off the cooldown rules AND returns to the original fixed -10 % stop (the chandelier is part of that
  component, see protocol). Its better numbers are therefore NOT attributable to the cooldown alone. It is descriptive, was not
  selected, and may not be adopted without a new protocol version and the single holdout.
- `no_exposure_limits` and (Trend) `no_circuit_breaker` equal R1: those limits never bound in that run.
- `no_vol_sizing` trades 31-38 times only: with plain stake proposals the exposure limits and the breaker dominate; not comparable.
- Bias: lookahead-analysis flags both R1 strategies in 2 of 4 evaluated periods (one trade each: SOL/USDT 2022-08-07, LINK/USDT
  2023-01-04). R0 strategies were clean in the same periods. The overlay is stateful (equity, cooldowns, breaker), which
  lookahead-analysis (full run versus truncated run) is not designed for, so a false positive is plausible, but it is NOT proven.
  Unit tests show appended future rows change no decision. T10 stays failed until a dedicated trade-level causality check exists.
- Remaining approximations: stress for R1 re-prices the identical base-cost positions (R0 stress had its own backtest);
  sizing-consistent slippage is a wallet-ratio approximation; overlay equity is Freqtrade fee-only equity at closed-candle prices;
  BTC regime history is read from the stored candle file (sliced to completed days before the decision time).
