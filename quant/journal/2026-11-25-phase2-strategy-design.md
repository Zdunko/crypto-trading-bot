# 2026-11-25 — Phase 2: strategy design and offline verification

- **Question:** Can we define simple, explainable strategies per family, with fixed pre-registered
  parameters, that are provably free of look-ahead on synthetic data and ready for Phase 3?
- **Branch:** `claude/freqtrade-trading-system-b82aek` · **Data:** none (synthetic candles in tests only)
- **Specs:** `quant/docs/strategies/` (written before any backtest) · **Thresholds proposal:** `phase3_validation_thresholds.md`

## Strategies (one section each; all long-only spot, 1h, stoploss -10 %, ROI exit disabled)

- **TrendEmaCross** — EMA(24)/EMA(120) cross; exit on cross back. Free parameters: 2.
- **MeanReversionRsiBb** — RSI<30 and close<BB(20,2σ) and sideways regime (ADX<25); exit above the middle
  band. Free parameters: 3. *Synthetic observation:* entries on ~0.33 % of candles in 40 random walks
  (96 000 candles) → possible **low trade count**; to be checked against T1 in Phase 3.
- **BreakoutDonchian** — close > prior 48-bar high with volume > 1.5× average; exit below prior 24-bar low.
  Free parameters: 3. Channel excludes the current candle (verified against a manual window).
- **MomentumRoc** — 240-bar ROC > 5 % and close > EMA(200); exit when ROC < 0. Free parameters: 3.
  Risk: immediate re-entry after a stop-out (no cooldown; Phase 4 protection).
- **BuyAndHold** — in-framework benchmark only (the Phase 3 benchmark is computed over all pairs).
- Shared: `market_regime` (ADX/EMA based) and `atr_stake_fraction` (volatility sizing, wired in Phase 4).

## Results (verified by running commands in this session)

- `bash quant/scripts/check.sh`: ruff clean, **124 passed**, config policy OK, strategy policy OK.
- `freqtrade list-strategies --strategy-path quant/strategies`: all 5 strategies load, status OK.
- One test failed on first run (`BreakoutDonchian` exit signal during warm-up). Cause: my test required
  *all* indicators defined, while the exit rule reads only the 24-bar `channel_low`. The strategy was
  correct; the test was over-specified and was changed to check each rule against **its own** inputs.
- Recursion test sensitivity: with `TrendEmaCross.startup_candle_count` lowered to 40 the relative
  difference is 1.8e-3 (> 1e-3 tolerance → test fails), at 130 it is 7.4e-4, at the declared 400 it is
  2.0e-4 → the test does detect too-short warm-ups.
- Workflow commands (`download-data`, `lookahead-analysis`, `recursive-analysis`) parse their arguments and
  stop only at market loading (no exchange access here).

## Interpretation (opinion)

- Causality and warm-up are verified on synthetic data only; that is necessary, not sufficient. The
  official Freqtrade bias checks on real candles (D4) are still **outstanding**.
- Nothing here says any strategy is profitable. No performance number exists.

## Assumptions & limitations

- `quant-bias-check.yml` had never run when this entry was first written. The Quant CI probe (run 45552884205)
  showed `api.binance.com` = 451 and OKX/Kraken/KuCoin/Gate/Coinbase/Binance-mirror = 200 from GitHub runners,
  so the workflow defaults to OKX. `workflow_dispatch` requires the file on the default branch, so the push
  trigger with `[bias-check]` in the commit message is used before merging.
- Parameter values are conventions (priors), not estimates; sensitivity ranges are for Phase 3 only.

## Decision / next step

Read the probe result, pick the data exchange, trigger the bias check, record command / commit / data hash
here, then request owner review of D1–D7 and the Phase 3 thresholds.

## D4 result — Freqtrade bias checks on real candles (verified from the workflow log)

- **Run:** `Quant bias check` #2, https://github.com/Zdunko/crypto-trading-bot/actions/runs/45553021957
  (job success, artifact `bias-check-af56964f…`, id 14994198659) · **Commit:** `af56964f842d02316e543bc888de44a0d78db78f`
- **Data:** OKX spot, 1h, public candles, no credentials. Pairs BTC/USDT, ETH/USDT, SOL/USDT, 39 317 candles
  each, downloaded from 2022-06-01; **data sha256 `83e0c636de1ab11473acc494421a25de4a312e478c4a9a3d3f12994046c268ea`**
  (hash of the sorted `*.feather` file hashes, computed in the run).
- **Analysis range:** `20230101-20240101`, fee 0.15 % per side (`configs/backtest.json`).
- **Commands (as in `quant-bias-check.yml`):** `freqtrade lookahead-analysis ... --strategy-list <4 strategies>
  --minimum-trade-amount 10 --targeted-trade-amount 20`; `freqtrade recursive-analysis ... --strategy <name> -p BTC/USDT
  --startup-candle 199 399 599 999`.

### lookahead-analysis (4 of 4 strategies: `has_bias = No`)

| Strategy | has_bias | signals analysed | biased entry | biased exit | biased indicators |
|---|---|---|---|---|---|
| TrendEmaCross | No | 20 | 0 | 0 | – |
| MeanReversionRsiBb | No | 20 | 0 | 0 | – |
| BreakoutDonchian | No | 20 | 0 | 0 | – |
| MomentumRoc | No | 20 | 0 | 0 | – |

All four also passed the workflow's strict gate (fails if a strategy is biased or was not evaluated).

### recursive-analysis (BTC/USDT only), variance in the strategy's own startup column

| Strategy | startup | worst indicator variance at that column |
|---|---|---|
| TrendEmaCross | 400 | `ema_slow` −0.002 % |
| MeanReversionRsiBb | 600 | `bb_lower`/`bb_middle` −0.000 % (rsi: none) |
| BreakoutDonchian | 100 | `volume_avg` 0.000 % |
| MomentumRoc | 600 | `ema_trend` 0.024 % |

All ≤ 0.1 % (acceptance threshold). Freqtrade also reported "No lookahead bias on indicators found" for each.
Note: `roc` shows `nan%` at startup 199 only because the 240-candle lookback cannot be computed there; it is "–"
(no variance) at the strategy's 600. Not a defect.

### Limits of this evidence (not hidden)

- Freqtrade's lookahead check is empirical (re-runs backtests on truncated data for 20 signals per strategy);
  absence of detected bias is **not a proof** of its absence.
- Recursive analysis used BTC/USDT only; lookahead used BTC, ETH, SOL over one year (2023) on **OKX** data.
- Positive side observation: MeanReversionRsiBb produced 20 analysable signals on real 2023 data, so it is not
  dead on real candles (unlike my fear from synthetic data). Trade count adequacy is still a Phase 3 question (T1).
- Still no backtest performance has been produced or reported.
