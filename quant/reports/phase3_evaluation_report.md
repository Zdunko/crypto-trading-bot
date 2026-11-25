# Phase 3 — evaluation report (period 2021-01-01 → 2025-07-01)

**Provenance.** Workflow `Quant research`, stage `[phase3-eval]`, run https://github.com/Zdunko/crypto-trading-bot/actions/runs/45563804911 (job 139033586367), commit `918c2f5b9992167b3776b13355f79f60dfa374f3`. Frozen protocol v2 (`quant/protocol/protocol.json`, manifest verified at start), dataset sha256 `fd94dcb6…8085` (verified in the job). The same numbers were produced by the earlier run 45561982317 (commit `fedad61`); this run only adds annualised intervals, a ruin flag and the reconciliation below. The report text between the lines is the unedited program output.

## Verdict

**All four strategies are REJECTED on the evaluation period. The holdout (2025-07-01 → 2026-11-25) was NOT evaluated and remains untouched**, as the protocol prescribes.

| Strategy | Failed criteria |
|---|---|
| TrendEmaCross | T1b, T3, T4, T5, T7b, T8 |
| MeanReversionRsiBb | T1b, T2, T3, T4, T5, T6, T7a, T7b, T8, T9 |
| BreakoutDonchian | T1b, T3, T4, T5, T6, T7a, T7b |
| MomentumRoc | T1b, T4, T5, T7a, T7b, T8 |

## Reading the result (interpretation, separate from the measurements)

- **T4 (max drawdown ≤ 20 %) and T5 (profit factor ≥ 1.3) fail for every strategy** (drawdown 75–87 %, PF 1.06–1.21 for the three that make money). The Phase-2 strategies are fully invested (up to 3 slots with the whole wallet, a fixed −10 % stop, no portfolio risk control), so a 20 % drawdown limit is out of reach by construction; that is a risk-management gap (Phase 4 topic), not something to be fixed by editing thresholds now.
- **Profit is concentrated** (T1b: one pair contributes 70–156 % of net profit; T7b: one 6-month window contributes 96–153 % of total profit). Most of the return comes from the 2021 and 2024-H2 bull windows; 2022 and 2025-H1 lose 30–44 %.
- **Mean reversion loses money outright** (−73.6 %, PF 0.73, losing in 8 of 9 windows, 0/6 parameter variants positive).
- **Momentum is the closest candidate** (passes T1a, T2, T3, T6, T9, T10) but is not close on drawdown, PF, concentration, window stability or bear-regime PF (0.44).
- **Costs matter:** fee-only (no slippage) TrendEmaCross would end at +795 % versus +654 % with base slippage and +218 % under stress.
- **The benchmark is hard to beat with selection luck in it:** equal-weight buy-and-hold +1896 % (Sortino 1.81, drawdown 89.7 %); Freqtrade's 3-slot BuyAndHold +4185 % only because the first three listed pairs include SOL — a reminder of survivorship/selection bias.
- **Uncertainty is large:** annualised-return intervals span roughly −18 %…+205 % (Trend), −13 %…+267 % (Momentum); none of the strategies' return-minus-benchmark intervals is clearly positive. Intervals are optimistic (see limitations).

## Reconciliation with Freqtrade's own totals (fee-only trades, no slippage layer)

Our equity reconstruction must reproduce Freqtrade's final balance and trade count; drawdown legitimately differs (ours is hourly mark-to-market including open positions; Freqtrade's uses closed trades and therefore **understates** drawdown).

| Strategy | Trades (Freqtrade / ours) | Final balance Freqtrade | Final equity ours | Difference | Max DD Freqtrade (closed trades) | Max DD ours (mark-to-market) |
|---|---|---|---|---|---|---|
| TrendEmaCross | 830 / 830 | 8949.82 | 8950.16 | +0.0038% | 41.3% | 70.1% |
| MeanReversionRsiBb | 780 / 780 | 430.20 | 430.20 | +0.0000% | 69.0% | 69.4% |
| BreakoutDonchian | 1033 / 1033 | 4049.01 | 4049.02 | +0.0002% | 76.9% | 79.3% |
| MomentumRoc | 523 / 523 | 13988.59 | 13988.99 | +0.0029% | 67.7% | 74.3% |
| BuyAndHold | 4 / 4 | 42885.70 | 42887.25 | +0.0036% | 0.0% | 61.3% |

## Program output

# Phase 3 results - evaluation period

- Protocol v2 (frozen), exchange `okx`, 1h candles, 8 pairs, dataset sha256 `fd94dcb657341422cb7109377585418d70cc25b5ed2f538454034b3e7bb58085`
- Period: 2021-01-01 -> 2025-07-01 (exclusive); simulated wallet 1000 USDT, max 3 open trades
- Costs per side: base fee 0.10% + slippage 0.05% (+0.05% on stop exits); stress fee 0.20% + slippage 0.10% (+0.10% on stops)
- Benchmark pairs (listed at period start): BTC/USDT, ETH/USDT, SOL/USDT, XRP/USDT, ADA/USDT, LINK/USDT, LTC/USDT, DOGE/USDT

## 1. Comparison (base costs)

| Strategy | Net return | Max DD | Sharpe | Sortino | PF | Win rate | Expectancy/trade | Trades | In market | Stress (net / PF) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| TrendEmaCross | 654.0% | 75.4% | 1.02 | 1.67 | 1.18 | 25.4% | 1.34% | 830 | 75% | 218.5% / 1.07 | REJECTED (T1b, T3, T4, T5, T7b, T8) |
| MeanReversionRsiBb | -73.6% | 82.4% | -0.80 | -0.92 | 0.73 | 57.8% | -0.38% | 780 | 18% | -100% (ruin; post-hoc slippage artefact) / 0.59 | REJECTED (T1b, T2, T3, T4, T5, T6, T7a, T7b, T8, T9) |
| BreakoutDonchian | 190.8% | 86.8% | 0.67 | 1.21 | 1.06 | 33.8% | 0.61% | 1033 | 68% | -60.3% / 0.98 | REJECTED (T1b, T3, T4, T5, T6, T7a, T7b) |
| MomentumRoc | 1140.2% | 77.7% | 1.10 | 1.95 | 1.21 | 30.0% | 3.22% | 523 | 71% | 643.6% / 1.13 | REJECTED (T1b, T4, T5, T7a, T7b, T8) |
| BuyAndHold | 4185.4% | 61.3% | 1.66 | 2.77 | inf | 100.0% | 2639.90% | 4 | 100% | 4182.8% / inf | reference |
| Equal-weight buy&hold (benchmark) | 1896.5% | 89.7% | 1.16 | 1.81 | n/a | n/a | n/a | - | n/a | 1890.5% / n/a | benchmark |
| BTC buy&hold | 269.4% | 77.2% | 0.78 | 1.16 | n/a | n/a | n/a | - | n/a | - | reference |

## 2. Criteria T1-T10 (frozen thresholds)

| Criterion | TrendEmaCross | MeanReversionRsiBb | BreakoutDonchian | MomentumRoc |
|---|---|---|---|---|
| T1a: closed trades (>= 200) | PASS 830.000 | PASS 780.000 | PASS 1033.000 | PASS 523.000 |
| T1b: max single-pair share of net profit (<= 0.3) | FAIL 0.703 | FAIL None | FAIL 1.560 | FAIL 0.842 |
| T2: net return after base costs (> 0) | PASS 6.540 | FAIL -0.736 | PASS 1.908 | PASS 11.402 |
| T3: Sortino vs benchmark (>= 1.806) | FAIL 1.666 | FAIL -0.921 | FAIL 1.205 | PASS 1.950 |
| T4: max drawdown (<= 0.200 (min of 0.2, benchmark)) | FAIL 0.754 | FAIL 0.824 | FAIL 0.868 | FAIL 0.777 |
| T5: profit factor (>= 1.3) | FAIL 1.177 | FAIL 0.727 | FAIL 1.062 | FAIL 1.209 |
| T6: stress: net return and profit factor (> 0 and >= 1.0) | PASS 2.185, 1.072 | FAIL -1.014, 0.585 | FAIL -0.603, 0.976 | PASS 6.436, 1.134 |
| T7a: share of windows with positive return (>= 0.6) | PASS 0.778 | FAIL 0.111 | FAIL 0.444 | FAIL 0.556 |
| T7b: largest window share of total profit (<= 0.5) | FAIL 1.099 | FAIL n/a | FAIL 1.533 | FAIL 0.961 |
| T8: profit factor per regime with enough trades (>= 0.8 where trades >= 30) | FAIL {'bear': 0.7350454462729521} | FAIL {'bear': 0.724053396008959, 'sideways': 0.6655247010235918} | PASS all ok | FAIL {'bear': 0.4415973962537002} |
| T9: share of parameter variants with net return > 0 (>= 0.75) | PASS 1.000 | FAIL 0.000 | PASS 0.833 | PASS 1.000 |
| T10: bias checks clean (lookahead + recursive) (True) | PASS True | PASS True | PASS True | PASS True |

## 3. Uncertainty (95% intervals; optimistic, see limitations)

| Strategy | Annualised return | Sortino | Sharpe | Sortino minus benchmark | Annualised return minus benchmark | Profit factor | Expectancy/trade |
|---|---|---|---|---|---|---|---|
| TrendEmaCross | [-17.9%, 205.4%] | [-0.03, 3.53] | [-0.02, 2.00] | [-1.57, 1.30] | [-255.4%, 69.0%] | [0.81, 1.67] | [0.2%, 2.8%] |
| MeanReversionRsiBb | [-43.8%, -3.9%] | [-1.68, -0.00] | [-1.53, -0.00] | [-4.21, -1.24] | [-390.3%, -6.7%] | [0.59, 0.91] | [-0.7%, -0.1%] |
| BreakoutDonchian | [-34.0%, 150.4%] | [-0.48, 2.97] | [-0.30, 1.55] | [-2.01, 0.72] | [-294.0%, 32.7%] | [0.81, 1.37] | [-0.1%, 1.4%] |
| MomentumRoc | [-12.9%, 266.5%] | [0.20, 3.84] | [0.13, 1.95] | [-1.25, 1.57] | [-221.7%, 96.2%] | [0.79, 1.74] | [0.8%, 6.4%] |
| BuyAndHold | [27.0%, 312.7%] | [1.08, 5.14] | [0.71, 2.63] | [-0.55, 2.88] | [-190.9%, 167.0%] | n/a | [114.9%, 7551.8%] |

trade-level bootstrap (iid) and circular block bootstrap (10-day blocks), n=2000, seed=20261125, 95% percentile intervals

## 4. Walk-forward windows (6 months, parameters fixed): return per window

- **TrendEmaCross**: 2021-01 248.0%; 2021-07 18.5%; 2022-01 -44.2%; 2022-07 16.1%; 2023-01 33.5%; 2023-07 15.1%; 2024-01 5.9%; 2024-07 165.3%; 2025-01 -34.6%
- **MeanReversionRsiBb**: 2021-01 -17.7%; 2021-07 -19.0%; 2022-01 -15.3%; 2022-07 -7.1%; 2023-01 -22.9%; 2023-07 -1.5%; 2024-01 -23.8%; 2024-07 4.8%; 2025-01 -17.1%
- **BreakoutDonchian**: 2021-01 292.5%; 2021-07 -4.6%; 2022-01 -32.2%; 2022-07 -32.0%; 2023-01 0.8%; 2023-07 3.4%; 2024-01 -11.4%; 2024-07 165.4%; 2025-01 -31.3%
- **MomentumRoc**: 2021-01 439.5%; 2021-07 63.2%; 2022-01 -41.6%; 2022-07 -30.6%; 2023-01 54.7%; 2023-07 89.1%; 2024-01 -18.4%; 2024-07 128.8%; 2025-01 -36.3%
- **BuyAndHold**: 2021-01 801.6%; 2021-07 245.1%; 2022-01 -17.9%; 2022-07 0.3%; 2023-01 6.2%; 2023-07 5.4%; 2024-01 -1.4%; 2024-07 47.9%; 2025-01 2.5%

## 5. Market regimes (BTC/USDT daily; trades by entry regime): trades / profit factor

- **TrendEmaCross**: bull 282 / 0.95; bear 193 / 0.74; sideways 355 / 1.64; unknown 0 / n/a
- **MeanReversionRsiBb**: bull 243 / 0.82; bear 158 / 0.72; sideways 379 / 0.67; unknown 0 / n/a
- **BreakoutDonchian**: bull 389 / 1.29; bear 196 / 0.90; sideways 448 / 0.89; unknown 0 / n/a
- **MomentumRoc**: bull 197 / 1.31; bear 110 / 0.44; sideways 216 / 1.46; unknown 0 / n/a
- **BuyAndHold**: bull 4 / inf; bear 0 / n/a; sideways 0 / n/a; unknown 0 / n/a

## 6. Parameter robustness (one parameter to each end of its range; base costs)

- **TrendEmaCross** (4/4 positive): ema_fast_period=12 147.5%; ema_fast_period=48 980.8%; ema_slow_period=72 1030.3%; ema_slow_period=200 362.6%
- **MeanReversionRsiBb** (0/6 positive): rsi_entry=20 -7.0%; rsi_entry=35 -100% (ruin; post-hoc slippage artefact); bb_period=14 -73.2%; bb_period=30 -78.1%; adx_max=20 -50.7%; adx_max=30 -90.3%
- **BreakoutDonchian** (5/6 positive): channel_period=24 27.5%; channel_period=96 591.5%; exit_period=12 -70.9%; exit_period=48 134.1%; volume_mult=1.0 170.5%; volume_mult=2.0 282.5%
- **MomentumRoc** (6/6 positive): roc_lookback=120 29.2%; roc_lookback=480 583.9%; roc_threshold=0.02 618.7%; roc_threshold=0.1 867.3%; ema_trend_period=100 1402.8%; ema_trend_period=300 1257.9%

## Exit reasons (base costs)

- TrendEmaCross: {'ema_cross_down': 794, 'stop_loss': 33, 'force_exit': 3}
- MeanReversionRsiBb: {'back_to_mean': 706, 'stop_loss': 74}
- BreakoutDonchian: {'donchian_breakdown': 988, 'stop_loss': 42, 'force_exit': 3}
- MomentumRoc: {'roc_negative': 446, 'stop_loss': 74, 'force_exit': 3}
- BuyAndHold: {'force_exit': 3, 'roi': 1}

## Limitations

- Candle-based backtest: entries/exits at candle open prices, stops filled at the stop price; real fills differ. Slippage is an assumption, not measured, and is not fed back into position sizing.
- Survivorship bias: the 8 pairs were chosen in 2026 and all still trade; delisted coins are absent, so results are optimistic by an unknown amount.
- Few independent regimes (about 4 years, one cycle); crypto pairs are highly correlated, so the effective sample is smaller than the trade count suggests. Bootstrap intervals assume the resampled blocks are representative and are therefore optimistic.
- Several strategies were tested; passing a threshold by chance is possible. No multiple-testing correction is applied beyond the pre-registered, strict thresholds.
