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

**Blocking prerequisite (owner decision):** where historical data is downloaded and backtests
run. Claude Code Cloud cannot reach any exchange. The probe job in `Quant CI` showed (2026-11-25) that GitHub
runners reach OKX, Kraken, KuCoin, Gate, Coinbase and the Binance data mirror, but **not** `api.binance.com`
(HTTP 451) and not Bybit (403). Default: run data work in GitHub Actions on OKX; the owner may instead
allow-list one exchange host for Claude Code Cloud. Bias checks in D4 need market data, so Phase 2 cannot close without this.

**Deliverables and acceptance criteria** (all must hold; each is checkable by a command or file):

| # | Deliverable | Acceptance criterion |
|---|---|---|
| D1 | One spec per family in `quant/docs/strategies/<name>.md`: trend following, mean reversion, breakout, momentum, plus a shared regime filter and a volatility risk component | Each spec states: hypothesis, exact entry/exit rules, **≤ 4 parameters with fixed values and allowed ranges written before any backtest**, favourable and unfavourable regimes, expected failure modes, cost sensitivity. |
| D2 | Strategies in `quant/strategies/` (one `IStrategy` per family) + a `BuyAndHold` benchmark strategy | `freqtrade list-strategies --strategy-path quant/strategies` lists all; each sets `stoploss`, keeps `can_short = False` and `position_adjustment_enable = False`; no `shift(-n)` or other future data. |
| D3 | Unit tests on synthetic candles | ≥ 3 tests per strategy: rule fires on a constructed pattern and not otherwise; **silent while the rule's own inputs are undefined (NaN warm-up)**; signals unchanged when future candles are removed (causality); indicators converge within `startup_candle_count` (offline analogue of recursive-analysis). `bash quant/scripts/check.sh` green, test count reported. |
| D4 | Bias checks | Run in GitHub Actions (`quant-bias-check.yml`, public data, no credentials): `lookahead-analysis` reports `has_bias = False` for every strategy (automated gate: a missing or biased strategy fails the job); `recursive-analysis` table archived with variance ≤ 0.1 % in the strategy's own startup column for every indicator (reviewed by hand — Freqtrade gives no pass/fail). Command, commit, data range and data hash recorded in the journal. |
| D5 | Safety extension | `quantlab.safety` statically rejects strategy files that enable shorting, position adjustment or omit `stoploss`; covered by tests. |
| D6 | Pre-registered Phase 3 thresholds | A proposal (for owner approval) of numeric "validated" criteria written **before** results exist: min. OOS trades, max drawdown, Sharpe/Sortino vs buy-and-hold, cost-stress multiple. |
| D7 | Housekeeping | Journal entry covering every strategy (one section each), `PROJECT_STATUS.md` updated, draft PR, Quant CI green, upstream-CI failures (if any) explained as upstream or ours. |

**Explicitly out of scope:** performance numbers, hyperopt, parameter tuning, ML. Backtests in
Phase 2 exist only as inputs to the bias checks and are not reported as performance.

**Exit:** D1–D7 satisfied and owner approves the PR.

## Phase 3 — Backtesting & validation pipeline (evaluation done 2026-11-25: no strategy validated; holdout untouched; awaiting owner review)
Authoritative definition: `quant/docs/strategies/phase3_validation_thresholds.md` and
`quant/protocol/protocol.json`. Stages (GitHub Actions, public OKX data, simulated capital):
1. **Data** — download + validate (done: 8 pairs, 0 gaps, hash recorded).
2. **Bias checks** — lookahead + recursive on 8 pairs × 6 periods inside the evaluation period.
3. **Evaluation** — 4 strategies + buy-and-hold benchmark, base and stress costs, 9 walk-forward windows,
   regimes, 22 robustness variants, bootstrap intervals; mechanical T1–T10 verdict.
4. **Holdout** — only for survivors, exactly once, files frozen by the manifest.
5. **Report** — comparative results, honest rejections; owner review.
No result may change a rule, parameter, threshold or period; "no strategy validated" is an acceptable outcome.

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
