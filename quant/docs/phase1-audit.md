# Phase 1 — Repository audit

Date: 2026-11-24 · Base commit: `7fcb509` (upstream `develop`, Freqtrade `2026.11-dev`)

Legend: **[V]** verified by running a command in this session · **[A]** assumption / not yet verified.

## 1. What the repository is

- [V] `Zdunko/crypto-trading-bot` is a **public GitHub fork of `freqtrade/freqtrade`**
  (default branch `develop`). It contains the full, unmodified upstream source; no project
  code existed before this phase.
- [V] Freqtrade version `2026.11-dev-7fcb509`, Python `>=3.12` (tested with 3.13.18),
  CCXT `4.5.94`, pandas 3.1, numpy 2.5, TA-Lib 0.8.3 (binary wheel, no system build needed).

## 2. Architecture (upstream Freqtrade)

| Area | Module | Relevance for us |
|---|---|---|
| Bot loop | `freqtrade/freqtradebot.py`, `worker.py` | Dry-run (paper) trading engine, Phase 5 |
| Strategy API | `freqtrade/strategy/interface.py` (`IStrategy`) | All strategies subclass this |
| Exchange | `freqtrade/exchange/` (CCXT wrapper, per-exchange classes) | Market metadata + data download |
| Data | `freqtrade/data/` (download, history, converters, dataprovider) | Historical OHLCV pipeline |
| Backtesting | `freqtrade/optimize/backtesting.py`, `optimize_reports/` | Phase 3 engine (event-driven, candle-based) |
| Hyperopt | `freqtrade/optimize/hyperopt/` (Optuna) | Use sparingly — overfitting risk |
| Bias checks | `freqtrade/optimize/analysis/` (`lookahead-analysis`, `recursive-analysis`) | Mandatory gate for every strategy |
| Protections | `freqtrade/plugins/protections/` (Cooldown, MaxDrawdown, StoplossGuard, LowProfitPairs) | Part of Phase 4 risk layer |
| Pairlists | `freqtrade/plugins/pairlist/` | Universe selection (survivorship-bias risk with dynamic lists) |
| Persistence | `freqtrade/persistence/` (SQLAlchemy, SQLite default) | Trade history for paper trading |
| RPC | `freqtrade/rpc/` (Telegram, Discord, webhook, FastAPI REST + FreqUI) | Notifications / mobile monitoring |
| ML | `freqtrade/freqai/` | Phase 6 only |
| Wallet | `freqtrade/wallets.py` | Simulated wallet in dry-run (`dry_run_wallet`) |

Built-in gaps we must fill ourselves: **slippage** (not modelled — we add a fee buffer),
**walk-forward validation** (not built in), **buy-and-hold benchmark per run** (only a
"market change" figure is reported), **daily loss limit / kill switch** policy, volatility sizing.

## 3. Dependencies

- [V] All runtime deps are exact-pinned in `requirements*.txt` and kept current upstream by
  Renovate. We reuse those pins (`quant/requirements.txt` → `-r ../requirements.txt`) so the
  project always runs on the versions upstream tests against.
- [V] Install with `uv` takes seconds; no system packages needed on Linux x86_64.
- Optional groups not installed by default (token/compute economy): `requirements-hyperopt.txt`
  (scikit-learn, optuna), `requirements-plot.txt` (plotly), `requirements-freqai*.txt`
  (lightgbm, xgboost, torch for RL). Add only when a phase needs them.

## 4. Security review

- [V] `.gitignore` already excludes `config*.json`, `user_data/*`, `.env`, `.venv`. Project
  configs therefore live in `quant/configs/` with non-`config*` names and empty credentials.
- [V] Repository is **public** → anything committed is world-readable, including research and
  strategy code. Secrets must never be committed; GitHub secret scanning is recommended.
- [V] Example configs contain placeholder keys only; no real secrets found by inspection.
- Upstream workflows pin actions by SHA and are audited by `zizmor`; our workflow follows the
  same pattern [V: `zizmor` reports no findings for `quant-ci.yml`].
- Risky features we disable by policy: live trading, futures/margin, `force_entry_enable`,
  `position_adjustment_enable`, exposed REST API with default credentials.
- New guardrail: `quant/quantlab/safety.py` fails CI on any config violating the hard rules.

## 5. Licensing

- [V] Freqtrade is **GPL-3.0-only**. Private use and modification are unrestricted.
- Because this fork is public, our code is distributed alongside GPL code; strategies and
  modules importing Freqtrade should be treated as GPL-3.0 and must keep the license file.
  Closed-source distribution of a modified Freqtrade is not allowed.
- Exchange data: Binance/other exchange terms apply to market data; historical OHLCV is
  used for private research only [A: no redistribution of raw data planned].

## 6. What runs where

| Task | Claude Code Cloud | GitHub Actions (public repo) |
|---|---|---|
| Install, lint, unit tests | [V] yes | [A] yes (workflow added, first run pending) |
| Upstream test suite | [V] runs (see status for result) | upstream `ci.yml` (15-job matrix) |
| Download exchange data | [V] **blocked** — all exchange hosts refused by network policy | [A] open internet; Binance may block US runners (HTTP 451) — probe job added |
| Backtesting | [V] **blocked** — needs exchange market metadata even with local data | [A] yes if an exchange API is reachable |
| Paper trading 24/7 | no (ephemeral container) | no (jobs max 6 h, not a server) |
| Mobile reporting | — | [A] static reports via Actions artifacts / GitHub Pages |

Consequences:
1. Research data download + backtests run **in GitHub Actions** (free for public repos), or the
   Claude Code environment gets a narrowly allow-listed exchange host (owner approval needed).
2. Continuous paper trading (Phase 5) needs an always-on host. Free options to evaluate later:
   Oracle Cloud Always Free ARM VM, or scheduled GitHub Actions "batch dry-run" simulations.

## 7. Upstream CI on the fork

- Upstream `ci.yml` runs a 15-job OS/Python matrix on **every pull request**, plus online
  exchange tests and Discord notifications (secrets absent → those steps fail/skip).
  Free on public repos but slow and noisy for our draft PRs.
- Recommendation: leave upstream workflow files untouched (avoid merge conflicts) and
  disable unneeded upstream workflows in the GitHub UI (Actions → workflow → "Disable
  workflow"). Our `quant-ci.yml` runs only on project changes.
- [A] GitHub disables Actions on new forks by default; the owner may need to enable them once.

## 8. Reproducible environment

```bash
bash quant/scripts/setup_env.sh   # uv venv + pinned deps + editable freqtrade
bash quant/scripts/check.sh       # ruff + pytest + safety policy
```

The same two commands run locally (Claude Code Cloud) and in GitHub Actions.
