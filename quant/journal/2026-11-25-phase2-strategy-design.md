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
