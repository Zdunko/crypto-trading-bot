# PROJECT STATUS

_Last updated: 2026-11-25 · Phase 1 approved. **Phase 2 in progress**: design + offline verification done, D4 (bias checks on real data) outstanding._

## Current state

| Item | State |
|---|---|
| Phase | 2 — Strategy research (in progress; Phase 1 approved by owner) |
| Branch / PR | `claude/freqtrade-trading-system-b82aek` · draft PR #1, not merged |
| Real-money trading | Disabled by policy; **no credentials exist anywhere** (see "Safety model") |
| Strategies | 4 specified + implemented (trend, mean reversion, breakout, momentum) + BuyAndHold benchmark; **none evaluated on market data** |
| Backtest results | **None** — no market data downloaded, no performance claims exist |
| Monthly cost | €0 |

## Verified results (commands actually run)

- `bash quant/scripts/check.sh` → ruff clean, **124 passed**, config policy OK, strategy policy OK
  (38 at first push → 46 after the audit fix → 124 with Phase 2 strategies and policy tests).
- mypy (upstream pre-commit hook, whole repo) → passed locally after the fix below.
- Upstream suite, local run before the audit fix (`pytest -n 4 --timeout=60`, excl. `tests/exchange_online`,
  `tests/freqai`): **4807 passed, 20 skipped, 6 failed**. The failure causes below are
  *attributed, not proven*; the GitHub CI matrix is the cross-check (see CI section):
  2× FreqAI model listing (optional FreqAI deps not installed), 2× `pip-audit` (tool not installed),
  1× file-permission test (container runs as root), 1× websocket invalid-URL test (timeout via sandbox proxy).
- `zizmor` on `quant-ci.yml` → no findings (also green in GitHub CI).
- Claude Code Cloud network: PyPI reachable, all exchanges refused. Backtesting got as far as the
  **unauthenticated** `GET /currencies` market-metadata call with no credentials, then failed on network.

## Phase 2 progress (acceptance criteria D1–D7 from `ROADMAP.md`)

| # | Status | Evidence / what is missing |
|---|---|---|
| D1 specs | done | `quant/docs/strategies/*.md` — 4 strategies, regime filter, volatility component; ≤ 3 free parameters each, fixed before any backtest |
| D2 strategies | done | 5 classes load via `freqtrade list-strategies` (status OK); spot, long only, no averaging, stoploss set |
| D3 unit tests | done | 124 tests: per-rule logic, NaN warm-up silence, causality (truncating the future changes nothing), offline recursion convergence |
| D4 bias checks | **outstanding** | Needs real candles. `quant-bias-check.yml` is written, zizmor-clean, arguments parse locally, but **never executed**; blocked on exchange reachability from GitHub runners (see probe job in Quant CI) |
| D5 strategy policy | done | `quantlab.strategy_policy` (AST) wired into `check.sh`: forbids shorting, averaging, leverage, negative `shift`, missing/too-wide `stoploss` (only `BuyAndHold` may use -0.99) |
| D6 thresholds | done (proposal) | `phase3_validation_thresholds.md` — T1–T10, awaiting **owner approval** before Phase 3 |
| D7 housekeeping | partly | journal written, status updated; CI results for the Phase 2 commit pending |

Known strategy risks (hypotheses, not results): mean reversion may yield too few trades (0.33 % of
synthetic candles); momentum can re-enter immediately after a stop-out (cooldown → Phase 4);
breakout slippage may exceed the 0.05 % buffer.

Synthetic-data tests prove rules and causality, **not profitability**. No backtest has been run.

## GitHub CI results

| Check | Commit `c6cc24a` | Commit `5c9582f` |
|---|---|---|
| Quant CI (ours) | success | success |
| zizmor | success | success |
| Upstream "Pre-commit checks" | **failed — caused by us** (mypy: duplicate module `conftest`, `quant/conftest.py` vs `tests/freqai/conftest.py`) | passed |
| Upstream "Build" gate | failed only because pre-commit failed | see below |
| Upstream test matrix (19 jobs) | cancelled | still running when audited; superseded by the audit commit |

Rule used to separate failures: a failure is **ours** if it names our files or disappears when our
change is removed; **upstream/environment** if it involves missing secrets (Discord, Coveralls, exchange
keys) or the unchanged upstream code. So far the only failure introduced by us was the mypy one, fixed.

## Safety model — what is and is not guaranteed

Guaranteed (tested):
- `quantlab.safety` rejects configs with `dry_run != true`, non-spot, margin, position adjustment,
  force entries, out-of-range `max_open_trades` / `tradable_balance_ratio` / `stoploss`, and committed secrets.
- **Audit finding (fixed):** Freqtrade lets `FREQTRADE__*` environment variables override the config
  (verified: `FREQTRADE__DRY_RUN=false` produced `dry_run: false`, `FREQTRADE__TRADING_MODE=futures` produced
  futures). The checker previously ignored them. It now overlays the environment exactly as Freqtrade does.
- Backtesting needs no paid service and no API keys (market metadata comes from public endpoints).

**Not** guaranteed (residual risk, honest list):
- The policy is a check run by `check.sh` / CI, **not a runtime lock**. `freqtrade trade -c <other config>`
  or a strategy class setting `position_adjustment_enable` / `can_short` bypasses it until roadmap item D5
  (static strategy check) and Phase 4 (runtime guard) exist.
- The only hard barrier against real orders is that **no exchange API key exists in the repo, the
  environment or this session**; live mode cannot place orders without one. Never add a key.

## Dependencies and reproducibility

- Direct runtime deps are exact-pinned (`==`) upstream and reused via `quant/requirements.txt`; test/lint tools pinned.
- **No lockfile for transitive deps:** in the audited venv 52 of 104 installed packages are not pinned
  (that venv also had hyperopt/plot extras). Builds are reproducible for pinned packages, not byte-identical.
  Recommendation: generate `uv pip compile` constraints before the Phase 3 data pipeline.
- Python 3.13 in our CI; upstream CI covers 3.12–3.14.

## GitHub Actions: security and cost

- `quant-ci.yml`: `permissions: contents: read`, `pull_request` (not `pull_request_target`), actions pinned by SHA,
  `persist-credentials: false`, no secrets, probe job uses only unauthenticated `curl`.
- **Upstream workflows remain active on the fork**, including scheduled ones (weekly `ci.yml`,
  `binance-lev-tier-update.yml`, which expects Binance key secrets that do not exist here). They are harmless
  without secrets but waste minutes and add noise. **Owner action recommended:** Actions → disable
  `binance-lev-tier-update`, `docker-update-readme`, `devcontainer-build`, `docker-build`, `packages-cleanup`,
  and optionally upstream `Freqtrade CI` (it runs a 19-job matrix on every push to this PR).
- Repository is public: everything committed is world-readable. Public-repo Actions minutes are free.

## Verified: exchange reachability from GitHub runners (probe job, run 45552884205, 2026-11-25)

| Endpoint | HTTP | | Endpoint | HTTP |
|---|---|---|---|---|
| `api.binance.com` | **451** (blocked) | | `api.exchange.coinbase.com` | 200 |
| `data-api.binance.vision` | 200 | | `api.kucoin.com` | 200 |
| `data.binance.vision` | 200 | | `api.gateio.ws` | 200 |
| `api.kraken.com` | 200 | | `api.bybit.com` | 403 |
| `www.okx.com` | 200 | | | |

Consequence: Freqtrade's `binance` exchange cannot be used from GitHub runners. `quant-bias-check.yml`
defaults to **OKX** for the technical bias check; this is **not** the owner's final data-exchange decision.
`configs/base.json` still says `binance`; the workflow overrides it with `FREQTRADE__EXCHANGE__NAME`.

## Not yet verified (assumptions)

- `quant-bias-check.yml` end-to-end (never executed). `workflow_dispatch` needs the file on the default branch; before merging use a push whose commit message contains `[bias-check]`.
- End-to-end data download + backtest (blocked here by network policy).
- Fee + slippage assumption of 0.15 % per side.

## Open decisions for the owner

1. Data/backtest location: GitHub Actions (free) and/or allow-list one exchange host in Claude Code Cloud.
2. Disable the upstream workflows listed above (recommended).
3. Exchange for Phase 3 research data: OKX is the working default (see reachability table); Kraken/KuCoin/Gate are alternatives. Binance only via a different host.

## Change log

- 2026-11-24 — Phase 1: audit, `AGENTS.md`, `ROADMAP.md`, journal, `quant/` layout, safety policy, configs, scripts, Quant CI.
- 2026-11-25 — fix: `quant/__init__.py` (mypy duplicate-module failure introduced by us).
- 2026-11-25 — final audit: environment-variable bypass closed (+8 tests), Phase 2 acceptance criteria D1–D7,
  residual-risk and CI documentation.
- 2026-11-25 — Phase 2 (approved): strategy specs, 5 strategies, `quant_common`, `strategy_policy`, 78 new tests,
  Phase 3 threshold proposal, `quant-bias-check.yml`, always-on informational network probe.
