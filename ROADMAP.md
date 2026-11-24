# ROADMAP

Each phase ends with a draft PR, a `PROJECT_STATUS.md` update and **owner approval** before
the next phase starts. Exit criteria are measurable; nothing is "done" on assumptions.

## Phase 1 — Repository audit & foundation ✅ (awaiting approval)
- Audit of Freqtrade architecture, deps, security, licensing, infrastructure → `quant/docs/phase1-audit.md`
- Project layout `quant/`, agent rules, roadmap, status, research journal
- Hard safety policy (`quant/quantlab/safety.py`) enforced in CI
- Reproducible env (`quant/scripts/setup_env.sh`) and quality gate (`quant/scripts/check.sh`)
- **Exit:** quality gate green locally and in GitHub Actions.

## Phase 2 — Strategy research (design, no tuning)
1. Decide data source/exchange using the CI network probe (Binance vs. alternatives).
2. Written spec per strategy family in `quant/docs/strategies/`: hypothesis, rules, parameters,
   expected regime, failure conditions:
   - Trend following (e.g. EMA crossover / Donchian trend with ATR stop)
   - Mean reversion (e.g. RSI / Bollinger re-entry, only in low-trend regimes)
   - Breakout (Donchian/volatility breakout with volume confirmation)
   - Momentum (time-series momentum / rate-of-change ranking)
   - Regime filter (e.g. 200-day trend + ADX/volatility state) as a shared component
   - Volatility risk layer (ATR stop distance, volatility-scaled stake)
3. Implement each as a small Freqtrade strategy in `quant/strategies/` with ≤ 4 parameters,
   plus `BuyAndHold` benchmark strategy.
4. Unit tests for signal logic on synthetic data; `lookahead-analysis` + `recursive-analysis` clean.
- **Exit:** strategies compile, pass bias checks, specs reviewed. No performance claims yet.

## Phase 3 — Backtesting & validation pipeline
1. Data: download OHLCV (1h + 1d, 2019→now) in GitHub Actions; store as workflow artifact or
   cached release asset (not in git); record data hash in the journal.
2. Universe: fixed list of pairs listed for the whole test period + documented survivorship
   caveat (delisted coins are absent from exchange data).
3. Costs: fee 0.10 % + 0.05 % slippage buffer per side (`backtest.json`), sensitivity at 2× costs;
   liquidity cap: stake ≤ small fraction of median candle quote volume.
4. `quantlab.metrics`: net return, max DD, Sharpe, Sortino, profit factor, win rate,
   expectancy, trades, monthly table, exposure — computed from Freqtrade result files.
5. `quantlab.validation`: in-sample / out-of-sample split, walk-forward (rolling windows),
   regime-segmented results (bull / bear / sideways by benchmark trend), parameter-stability grid.
6. Report generator → Markdown/HTML readable on a phone; benchmark = buy-and-hold, equal weight.
- **Exit:** reproducible pipeline (`workflow_dispatch`) producing a report from a pinned commit
  and data hash; a strategy is "validated" only if OOS/walk-forward beats buy-and-hold on a
  risk-adjusted basis (Sharpe/Sortino, max DD) with acceptable trade count.

## Phase 4 — Risk management
- Config + strategy-level controls: max position exposure, portfolio exposure cap,
  max daily loss, max drawdown (protections + custom guard), volatility-based sizing
  (`custom_stake_amount`), emergency kill switch (file/env flag → stop entries), automatic
  suspension on abnormal behaviour (error rate, data gaps, slippage outliers).
- Extend safety policy to statically inspect strategies (no position adjustment, stoploss set).
- **Exit:** every control covered by unit tests and a backtest scenario that triggers it.

## Phase 5 — Paper trading (dry-run only)
- Choose free always-on host (candidate: Oracle Cloud Always Free) — **owner approval**.
- Dry-run deployment with SQLite trade history, strategy version tag (git SHA) per trade,
  structured error logs, Telegram notifications (token via env var only), daily mobile report.
- **Exit:** ≥ 4 weeks of uninterrupted dry-run with live-vs-backtest deviation report.

## Phase 6 — Advanced research (conditional)
- Only if Phase 3–5 baseline is validated: FreqAI / ML / ensembles evaluated with the same
  walk-forward protocol. Adopt only with measurable, robust out-of-sample improvement.

## Out of scope (permanent unless the owner changes the rules)
Live trading with real funds, leverage, futures, margin, shorting, martingale,
unbounded DCA, paid APIs or infrastructure without approval.
