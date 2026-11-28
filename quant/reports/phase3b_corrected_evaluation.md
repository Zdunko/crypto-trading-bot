# Phase 3B - corrected evaluation (sizing-consistent slippage)

**This does NOT replace `phase3_evaluation_report.md`** (original, post-hoc slippage, preserved unchanged). Same period (2021-01-01 -> 2025-07-01), same data (sha256 `fd94dcb6...8085`), same frozen strategies/thresholds; only the cost engine differs (`quantlab.costs.apply_costs_consistent`). Provenance: workflow `Quant research` stage `[phase3b-audit]`, run https://github.com/Zdunko/crypto-trading-bot/actions/runs/45630084090 (job 139260602324), commit `065a7fcaac67af93c39ca90444f2a24cf0550638`. Holdout not evaluated.

Unedited program output follows.

# Phase 3 results - evaluation period

- Protocol v2 (frozen), exchange `okx`, 1h candles, 8 pairs, dataset sha256 `fd94dcb657341422cb7109377585418d70cc25b5ed2f538454034b3e7bb58085`
- Period: 2021-01-01 -> 2025-07-01 (exclusive); simulated wallet 1000 USDT, max 3 open trades
- Costs per side: base fee 0.10% + slippage 0.05% (+0.05% on stop exits); stress fee 0.20% + slippage 0.10% (+0.10% on stops)
- Benchmark pairs (listed at period start): BTC/USDT, ETH/USDT, SOL/USDT, XRP/USDT, ADA/USDT, LINK/USDT, LTC/USDT, DOGE/USDT

## 1. Comparison (base costs)

| Strategy | Net return | Max DD | Sharpe | Sortino | PF | Win rate | Expectancy/trade | Trades | In market | Stress (net / PF) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| TrendEmaCross | 583.3% | 72.2% | 1.02 | 1.67 | 1.18 | 25.4% | 1.34% | 830 | 75% | 207.9% / 1.09 | REJECTED (T1b, T3, T4, T5, T7b, T8) |
| MeanReversionRsiBb | -66.5% | 75.3% | -0.86 | -0.99 | 0.73 | 57.8% | -0.38% | 780 | 18% | -83.4% / 0.59 | REJECTED (T1b, T2, T3, T4, T5, T6, T7a, T7b, T8, T9) |
| BreakoutDonchian | 188.5% | 82.2% | 0.67 | 1.21 | 1.07 | 33.8% | 0.61% | 1033 | 68% | 6.8% / 1.00 | REJECTED (T1b, T3, T4, T5, T7a, T7b) |
| MomentumRoc | 1074.0% | 75.5% | 1.11 | 1.97 | 1.22 | 30.0% | 3.22% | 523 | 71% | 610.5% / 1.15 | REJECTED (T1b, T4, T5, T7a, T7b, T8) |
| BuyAndHold | 4185.1% | 61.3% | 1.66 | 2.77 | inf | 100.0% | 2639.90% | 4 | 100% | 4182.1% / inf | reference |
| Equal-weight buy&hold (benchmark) | 1896.5% | 89.7% | 1.16 | 1.81 | n/a | n/a | n/a | - | n/a | 1890.5% / n/a | benchmark |
| BTC buy&hold | 269.4% | 77.2% | 0.78 | 1.16 | n/a | n/a | n/a | - | n/a | - | reference |

## 2. Criteria T1-T10 (frozen thresholds)

| Criterion | TrendEmaCross | MeanReversionRsiBb | BreakoutDonchian | MomentumRoc |
|---|---|---|---|---|
| T1a: closed trades (>= 200) | PASS 830.000 | PASS 780.000 | PASS 1033.000 | PASS 523.000 |
| T1b: max single-pair share of net profit (<= 0.3) | FAIL 0.631 | FAIL None | FAIL 1.453 | FAIL 0.846 |
| T2: net return after base costs (> 0) | PASS 5.833 | FAIL -0.665 | PASS 1.885 | PASS 10.740 |
| T3: Sortino vs benchmark (>= 1.806) | FAIL 1.669 | FAIL -0.985 | FAIL 1.214 | PASS 1.970 |
| T4: max drawdown (<= 0.200 (min of 0.2, benchmark)) | FAIL 0.722 | FAIL 0.753 | FAIL 0.822 | FAIL 0.755 |
| T5: profit factor (>= 1.3) | FAIL 1.184 | FAIL 0.726 | FAIL 1.072 | FAIL 1.218 |
| T6: stress: net return and profit factor (> 0 and >= 1.0) | PASS 2.079, 1.090 | FAIL -0.834, 0.591 | PASS 0.068, 1.004 | PASS 6.105, 1.153 |
| T7a: share of windows with positive return (>= 0.6) | PASS 0.778 | FAIL 0.111 | FAIL 0.444 | FAIL 0.556 |
| T7b: largest window share of total profit (<= 0.5) | FAIL 0.977 | FAIL n/a | FAIL 1.522 | FAIL 0.876 |
| T8: profit factor per regime with enough trades (>= 0.8 where trades >= 30) | FAIL {'bear': 0.752690895381355} | FAIL {'bear': 0.7011933272426014, 'sideways': 0.6791855393333988} | PASS all ok | FAIL {'bear': 0.44562086863270994} |
| T9: share of parameter variants with net return > 0 (>= 0.75) | PASS 1.000 | FAIL 0.000 | PASS 0.833 | PASS 1.000 |
| T10: bias checks clean (lookahead + recursive) (True) | PASS True | PASS True | PASS True | PASS True |

## 3. Uncertainty (95% intervals; optimistic, see limitations)

| Strategy | Annualised return | Sortino | Sharpe | Sortino minus benchmark | Annualised return minus benchmark | Profit factor | Expectancy/trade |
|---|---|---|---|---|---|---|---|
| TrendEmaCross | [-15.7%, 179.4%] | [-0.05, 3.51] | [-0.03, 1.99] | [-1.59, 1.29] | [-265.0%, 58.8%] | [0.83, 1.67] | [0.2%, 2.8%] |
| MeanReversionRsiBb | [-37.5%, -3.2%] | [-1.74, -0.03] | [-1.58, -0.03] | [-4.26, -1.32] | [-385.4%, -2.2%] | [0.58, 0.92] | [-0.7%, -0.1%] |
| BreakoutDonchian | [-27.6%, 128.1%] | [-0.47, 3.03] | [-0.29, 1.56] | [-1.97, 0.76] | [-301.2%, 27.6%] | [0.80, 1.39] | [-0.1%, 1.4%] |
| MomentumRoc | [-11.1%, 244.7%] | [0.19, 3.85] | [0.13, 1.95] | [-1.24, 1.57] | [-228.8%, 87.1%] | [0.80, 1.75] | [0.8%, 6.4%] |
| BuyAndHold | [27.0%, 312.7%] | [1.08, 5.14] | [0.71, 2.63] | [-0.55, 2.88] | [-190.9%, 167.0%] | n/a | [114.9%, 7551.8%] |

trade-level bootstrap (iid) and circular block bootstrap (10-day blocks), n=2000, seed=20261125, 95% percentile intervals

## 4. Walk-forward windows (6 months, parameters fixed): return per window

- **TrendEmaCross**: 2021-01 247.3%; 2021-07 19.2%; 2022-01 -40.8%; 2022-07 13.5%; 2023-01 28.2%; 2023-07 12.7%; 2024-01 5.3%; 2024-07 134.7%; 2025-01 -31.2%
- **MeanReversionRsiBb**: 2021-01 -17.2%; 2021-07 -18.2%; 2022-01 -13.8%; 2022-07 -6.2%; 2023-01 -18.8%; 2023-07 -1.1%; 2024-01 -17.2%; 2024-07 3.1%; 2025-01 -10.7%
- **BreakoutDonchian**: 2021-01 286.9%; 2021-07 -2.9%; 2022-01 -28.7%; 2022-07 -26.3%; 2023-01 0.8%; 2023-07 2.0%; 2024-01 -7.4%; 2024-07 104.6%; 2025-01 -24.9%
- **MomentumRoc**: 2021-01 438.9%; 2021-07 62.2%; 2022-01 -39.6%; 2022-07 -27.6%; 2023-01 46.4%; 2023-07 78.3%; 2024-01 -16.6%; 2024-07 113.2%; 2025-01 -33.8%
- **BuyAndHold**: 2021-01 801.6%; 2021-07 245.1%; 2022-01 -17.9%; 2022-07 0.3%; 2023-01 6.2%; 2023-07 5.4%; 2024-01 -1.4%; 2024-07 47.9%; 2025-01 2.5%

## 5. Market regimes (BTC/USDT daily; trades by entry regime): trades / profit factor

- **TrendEmaCross**: bull 282 / 1.00; bear 193 / 0.75; sideways 355 / 1.60; unknown 0 / n/a
- **MeanReversionRsiBb**: bull 243 / 0.81; bear 158 / 0.70; sideways 379 / 0.68; unknown 0 / n/a
- **BreakoutDonchian**: bull 389 / 1.31; bear 196 / 0.87; sideways 448 / 0.91; unknown 0 / n/a
- **MomentumRoc**: bull 197 / 1.34; bear 110 / 0.45; sideways 216 / 1.46; unknown 0 / n/a
- **BuyAndHold**: bull 4 / inf; bear 0 / n/a; sideways 0 / n/a; unknown 0 / n/a

## 6. Parameter robustness (one parameter to each end of its range; base costs)

- **TrendEmaCross** (4/4 positive): ema_fast_period=12 137.5%; ema_fast_period=48 903.5%; ema_slow_period=72 906.3%; ema_slow_period=200 354.1%
- **MeanReversionRsiBb** (0/6 positive): rsi_entry=20 -6.9%; rsi_entry=35 -91.1%; bb_period=14 -66.7%; bb_period=30 -67.8%; adx_max=20 -49.0%; adx_max=30 -78.8%
- **BreakoutDonchian** (5/6 positive): channel_period=24 57.3%; channel_period=96 537.3%; exit_period=12 -42.6%; exit_period=48 129.5%; volume_mult=1.0 165.0%; volume_mult=2.0 264.0%
- **MomentumRoc** (6/6 positive): roc_lookback=120 51.1%; roc_lookback=480 561.4%; roc_threshold=0.02 586.2%; roc_threshold=0.1 830.1%; ema_trend_period=100 1319.2%; ema_trend_period=300 1176.6%

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
