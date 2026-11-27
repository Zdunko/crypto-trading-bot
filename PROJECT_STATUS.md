# PROJECT STATUS

_Last updated: 2026-11-25 · Phase 3 evaluation complete: **no strategy validated**, holdout untouched. Awaiting owner review; Phase 4 not started._

## Current state

| Item | State |
|---|---|
| Phase | 4 — Risk-management research finished (report below), awaiting owner review; holdout untouched |
| Branch / PR | `claude/freqtrade-trading-system-b82aek` · draft PR #1, not merged |
| Real-money trading | Disabled by policy; **no credentials exist anywhere** (see "Safety model") |
| Strategies | 4 specified + implemented (trend, mean reversion, breakout, momentum) + BuyAndHold benchmark; **none evaluated on market data** |
| Backtest results | Evaluation 2021-01 → 2025-07 on OKX data: **all four strategies rejected** (see Phase 3 outcome); holdout 2025-07 → 2026-11 untouched |
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
| D4 bias checks | done (with limits) | Run #2 of `quant-research.yml` (bias stage) (https://github.com/Zdunko/crypto-trading-bot/actions/runs/45553021957, commit `af56964`, OKX data, sha256 `83e0c636…68ea`): lookahead **no bias for 4/4** (20 signals each, 0 biased); recursive variance ≤ 0.024 % in each strategy's own startup column. Empirical, not a proof; recursive check on BTC/USDT only. Details in the journal |
| D5 strategy policy | done | `quantlab.strategy_policy` (AST) wired into `check.sh`: forbids shorting, averaging, leverage, negative `shift`, missing/too-wide `stoploss` (only `BuyAndHold` may use -0.99) |
| D6 thresholds | done (proposal) | `phase3_validation_thresholds.md` — T1–T10, awaiting **owner approval** before Phase 3 |
| D7 housekeeping | partly | journal and status updated; Quant CI green on `497e0b4` and `af56964`; upstream matrix red only from the missing `CODECOV_TOKEN` (commented on PR); owner review pending |

Known strategy risks (hypotheses, not results): mean reversion may yield too few trades (0.33 % of
synthetic candles); momentum can re-enter immediately after a stop-out (cooldown → Phase 4);
breakout slippage may exceed the 0.05 % buffer.

Synthetic-data tests prove rules and causality, **not profitability**. No backtest has been run.

## Phase 3 outcome (verified from workflow logs; full report: `quant/reports/phase3_evaluation_report.md`)

- Protocol v2 frozen at commit `6a80519` (T1 ≥ 200 trades, T4 ≤ 20 % and ≤ benchmark, T5 ≥ 1.3; rest unchanged; fee and slippage counted once; untouched holdout). Data: OKX, 8 pairs, 0 gaps, hash `fd94dcb6…8085`.
- Bias checks (8 pairs × 6 periods): clean for all four strategies (run 45560148402).
- Evaluation (run 45563804911, commit `918c2f5`): TrendEmaCross +654 %, MeanReversionRsiBb −73.6 %, BreakoutDonchian +191 %, MomentumRoc +1140 % net, versus equal-weight buy-and-hold +1896 %; max drawdowns 75–87 % versus the 20 % limit. **All four rejected**; failures: Trend T1b/T3/T4/T5/T7b/T8, MeanReversion 10 criteria, Breakout T1b/T3/T4/T5/T6/T7a/T7b, Momentum T1b/T4/T5/T7a/T7b/T8.
- Reconciliation with Freqtrade's own balances: within 0.004 %, identical trade counts. Holdout **not evaluated**.
- Honest limits: post-hoc slippage is not fed back into sizing (artefact only for near-ruined accounts), flat slippage assumption, survivorship bias, one market cycle, optimistic bootstrap intervals.
- Upstream CI: Codecov upload patched (one condition); the first full matrix exposed a Windows-only bug in our manifest paths (fixed, `5126a25`). The matrix for the latest commit was not re-verified after the last push; one upstream job ("Online / live tests", ccxt against live exchanges) was reported failed on `918c2f5` and has **not** been investigated.

## Phase 3B (audit) - see `quant/docs/phase3b/audit_findings.md`

- Slippage artefact fixed additively (`apply_costs_consistent`); originals preserved; all four strategies still rejected; Breakout T6 flips to PASS but it fails six other criteria.
- Native Freqtrade reconciliation: trades, PF, win rate, profit and per-pair profit identical.
- Thresholds were applied to the pre-holdout period only (leakage proof), but there was no development/OOS split: all data before 2025-07-01 is research data.
- Benchmark: +1896 % is dominated by SOL (66.7 %) and DOGE (22.6 %) and by the 2021-01-01 start; Freqtrade BuyAndHold +4185 % is one SOL x100 ROI exit.
- TrendEmaCross and MomentumRoc: research candidates only. Risk-management research **proposal awaiting approval** (`quant/docs/phase3b/risk_research_proposal.md`); nothing implemented.

### Decisions that belong to the owner
1. Accept "no validated strategy" as the Phase 3 result, or approve a **new protocol version** for redesigned strategies (e.g. with portfolio-level risk limits from Phase 4). Note: the evaluation period has now been seen, so the untouched holdout is the only clean sample left and can be used once.
2. Whether T4 (20 % drawdown) remains the right gate for a fully invested long-only crypto strategy, or whether the exposure/sizing rules should be added to the strategies first.

## Phase 4 outcome (research data, diagnostics only; full report `quant/reports/phase4_risk_research_report.md`)

- R1 overlay implemented (`quant/strategies_r1/`), 31 overlay tests + 12 engine tests, protocol v3 frozen before the run, 14 backtests, holdout untouched.
- Run 1 was INVALID (overlay equity bug, found by cross-checking the breaker against reconstructed equity; fixed, errata in `protocol_v3.json`). Run 2 is the reported one. 2 of 3 CI runs used.
- Result: R1 TrendEmaCross -19.0 % (DD 21.8 %), MomentumRoc -14.8 % (DD 23.1 %); R0 was +583 % / +1074 % with DD ~72-76 %. R1 fails T2-T8 and T10; T9 not evaluated. Lower drawdown, but negative after costs and still above the 20 % limit.
- Bias: lookahead flags 1 trade in 2 of 4 periods for both R1 strategies (R0 was clean); likely overlay state-dependence but unproven, so T10 failed.
- Ablations are descriptive and unselected; `no_stop_cooldown` (also reverts the chandelier to the fixed -10 % stop) looks better but is not attributable to one component and may not be adopted without a new protocol and the single holdout.
- Upstream `Build (3.13)` fails only because 6 macOS jobs never get a runner (17 other jobs pass); not our change.

## Phase 4B / Stage 0 (infrastructure only; report `quant/docs/phase4b/stage0_report.md`)

- Approved by owner: Stage 0 only; Family A (HTF trend, volatility targeting, crypto/cash) prioritised; all Phase 4 configurations incl. `no_stop_cooldown` remain rejected.
- Added: single execution/cost engine (`quantlab/execution.py`), continuous deterministic circuit breaker, trade-level causality checks (`causality.py`), statistical rules fixed in advance (`stats.py`, `protocol_v4_stats.json`), reconstructed experiment ledger (40 distinct configurations, 136 backtests, 0 holdout evaluations), manifest v4.
- Reconciliation with native Freqtrade on synthetic fixtures: identical trades and timestamps, profit within 3.3e-4 USDT per 100 USDT stake; documented stop-gap rule difference.
- No strategy, no profitability backtest, holdout untouched. Family A proposal awaits approval.

## Family A (implementation done, NO market evaluation; `quant/docs/family_a/implementation_report.md`)

- Owner decisions 2026-11-25: breaker ON in all evaluations (impact reported separately); halt cancels entries, liquidates with fees/slippage/liquidity cap, no auto restart; implementation and evaluation separately approved.
- Implemented `quantlab/family_a.py` (A1, A0, V0) on the Stage 0 engine, spec frozen in `protocol_v5_family_a.json` + manifest v5. 318 tests pass locally. Evaluation awaits approval.

## Family A evaluation outcome (CI run 45679466940; report `quant/reports/family_a/evaluation_report.md`)

- One research run, evaluation period only, holdout untouched. Liquidity correction A1 applied first (completed-candle median volume), original manifests preserved, amendments A1/A2 recorded.
- A1 +24.4 %, A0 +24.0 %, V0 +30.0 % (base costs, breaker ON) versus B1 +1896 %; every variant fails T1 (14/7/8 episodes), T3, T4, T7, T1b; T10 (causality) passes; T9 not evaluated; T6 passes for A1 only. DSR 0.10-0.20, Holm rejects nothing, PBO 0.47: "not_credible".
- The terminal 20 % breaker halted each variant early (A1 after 48.6 % of the period, V0 8.7 %, A0 0.6 %), so most of the period was spent in cash; the evaluation says little about the signal across a full cycle.
- Recommendation: do not use Family A as specified for the holdout. Further research only after an owner decision on the evaluation design (not on parameters).

## Phase 4C proposal (design only; `quant/docs/phase4c/risk_and_evaluation_protocol_v2_proposal.md`)

- Owner accepted the rejection of Family A. Proposal: four-layer separation, tiered breaker (temporary reduction / defensive flatten with cooldown and staged re-entry / manual emergency shutdown), shadow-replay diagnostics, risk-matched benchmarks, feasibility gate, hard research budget. Family B judged not justified on current data. Nothing implemented; awaiting approval gate G0.

## Phase 4C S1 data audit (`quant/docs/phase4c/s1_data_audit_report.md`)

- Binance Vision archive keeps delisted symbols; a point-in-time universe of >= 30 liquid USDT assets is reconstructible from 2021-01 (84 at 1 M, 40 at 5 M median daily volume), with survivorship, identity, single-venue, no-order-book and CC BY-NC-SA licence caveats. Other free sources unsuitable. S2 GO (no data dependency); Family B and new market evaluation NO-GO until feasibility gate, identity table and full quality scan exist.

## Phase 4C S2 (risk layer V2; `quant/docs/phase4c/s2_risk_v2_specification.md`)

- Implemented the tiered state machine, persistence, manual authorisation, risk budget, active-window statistics and the order-level wrapper; synthetic validation only (466 local tests). Manifest v6; amendment A4 (causality helper). No market evaluation; Family A remains rejected; all risk numbers provisional.

## Phase 4C S2 freeze and S3 data feasibility gate (`quant/protocol/s2_freeze_record.json`, `quant/docs/phase4c/s3_feasibility_report.md`)

- S2 frozen at commit `6d24202` (manifest v6, config hash, CI evidence in the freeze record; guarded by `tests/test_s2_freeze.py`); risk parameters and T1-T10 unchanged.
- S3 (development-period data only, holdout never requested): pre-registered criteria (`s3_criteria.json`, commit `325aa33`) all pass -> **CONDITIONAL GO** for Binance Vision as a non-commercial research dataset: 21 518 daily files, 100 % checksum match, 0.014 % daily files quarantined, hourly sample (369 files) defect upper bound 1.95 %, >= 84 PIT-eligible assets at 1 M at every month start 2021-01..2025-06 (83 after identity exclusions), delisted assets retained (26-45 % of eligible cohorts later delisted), deterministic reproduction, 0.43 GB / 0.17 h for 1h data. Licence read from the primary Vision Dataset Terms: personal non-production backtesting permitted; live/paper/commercial/signal distribution not. Risk-layer x Freqtrade integration validation is design only (`s3_risk_integration_plan.md`). Ledger amendment A6. Family A stays rejected, Family B NO-GO, no market evaluation. Unresolved: identity table, whole-sample exclusion look-ahead, volume-only liquidity, one cycle (2 bear episodes), hourly quality sampled only, alternative sources unverifiable here.

## Phase 4C S4 point-in-time dataset builder (`quant/docs/phase4c/s4_dataset_builder_report.md`, `quant/dataset/`)

- Pre-registered criteria (`s4_criteria.json`, commit `58ba372`): all 16 gates pass -> GO for a research-only dataset. Development window 2017-08..2025-06 only; 593 USDT symbols, 43 036 files (daily and hourly, complete scan), 11 quarantined with reason codes, 636 identity epochs, explicit asset classification (no regex), causal liquidity eligibility; causality verified on the real data (prefix invariance and adversarial future perturbation), deterministic dataset hash `462288b1...` reproduced by an independent build, archive stable against the S3 pins (21 518/21 518). Licensing alternatives investigated as documentation only: nothing but Binance Vision is verified, and it is research-only. Ledger amendment A7. No market evaluation; Family A rejected; Family B not approved; risk parameters and T1-T10 unchanged.

## Phase 4C S5-infra (`quant/docs/phase4c/s5_report.md`)

- The original S5 (first new family evaluation) needs a market evaluation and is NOT executed. Done: S4 dataset frozen (`protocol/s4_freeze_record.json`), limitations register (macOS cancelled jobs = unresolved infrastructure limitation, not passed tests), X1 investigation (eligibility unaffected, execution effect unbounded), identity review (conservative handling costs 0.07 % of decisions), holdout-isolation statement (with exposures), production-data licensing roadmap, causal fail-closed dataset loader + universe guard + research-budget enforcement (synthetic validation, 540 tests), ledger amendment A8. Still missing from the original plan: feasibility-gate tool and benchmark add-ons.

## Phase 4C S6 feasibility gate and benchmark infrastructure (`quant/docs/phase4c/s6_report.md`)

- S5-infra frozen (`protocol/s5_freeze_record.json`). Built with synthetic fixtures only: machine-readable pre-registration template and deterministic fail-closed feasibility gate (`quantlab/feasibility.py`; rejects Family A as specified, passes a synthetic example, never authorises a run), benchmark registry and engine-based benchmarks (cash, BTC buy-and-hold, point-in-time equal weight, simple trend, volatility-targeted, exposure-/volatility-matched, cash-mix at T4, random-timing null) with comparison statistics and Holm; risk review of stale held positions (frozen S2 layer fails safe for new risk but is blind to the loss of a delisted holding; recorded L-STALEPOS); design-only proposal for the next family (B2: cross-sectional momentum on the point-in-time universe; nothing implemented, budget unchanged N 43, 0 families); amendment A9. Original S5 (market evaluation) still unapproved.

## Phase 4C S7 risk integrity and research methodology review (`quant/docs/phase4c/s7_report.md`)

- S6 accepted and frozen (`protocol/s6_acceptance_record.json`); budget unchanged (N 43/52, 0 families). **Risk layer V3** (`quantlab/risk_v3.py`, spec `protocol/risk_v3_spec.json`, 51 synthetic tests; `risk_v2.py` untouched): elapsed-time stale detection (48 h), hourly monitoring independent of the strategy clock, explicit DELISTED/SUSPENDED/UNTRADEABLE/MISSING handling, conservative valuation that cannot hide drawdown, zero/partial-recovery sensitivity, identical to V2 when nothing is impaired; not yet used by any evaluation. **Gate methodology audit** (synthetic simulations, stored): v1 gate overstates effective episodes under overlap/regimes, exposure-favouring statistic, cannot check declared exposure; v2 proposal not adopted. **Family review**: B2 and three candidates, recommendation NO-GO (minimum detectable relative IR ~1.2 on 4.5 years). Production-readiness roadmap (documentation). Amendment A10, natural-order amendment loading fix. Original S5 and B2 remain unapproved.

## Phase 4C S8 research feasibility resolution and methodology redesign (`quant/docs/phase4c/s8_report.md`)

- Pre-registered (`s8_criteria.json`, commit a54ff97) before any code. **Decision: NO-GO under the pre-registered rule** (`s8_decision_framework.md`): no path reaches 80 % power at IR 0.5 (4.5 y: 0.22-0.33; 13 y: 0.49-0.56; ~25 y needed) and the only verified data licence is research-only. Synthetic study (`quantlab/design_study.py`, stored results, 11 tests): HAC and block L10 keep size <= 0.07; dependence inflation of return series is small (0.97-1.23); non-significance is not evidence of negative performance; shuffled K-fold leaks (+0.085 IC on noise); more assets are 1.4-1.7 effective assets for absolute claims; cross-sectional breadth helps only through the achievable IR (assumed); best-of-43 null Sharpe 1.04.
- Licensing: 12 primary URLs unreachable (host not resolvable) -> all venues except Binance Vision remain **unverified**. Risk V3: not ready for adoption (needs integration tests G1, G3, G5 and an owner decision on recovery). v2 methodology proposal still not adopted. S6 gate, thresholds, T1-T10, manifests, budget (N 43/52), holdout all unchanged. No strategy, no market evaluation.

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

Consequence: Freqtrade's `binance` exchange cannot be used from GitHub runners. `quant-research.yml` (bias stage)
defaults to **OKX** for the technical bias check; this is **not** the owner's final data-exchange decision.
`configs/base.json` still says `binance`; the workflow overrides it with `FREQTRADE__EXCHANGE__NAME`.

## Not yet verified (assumptions)

- `quant-research.yml` (bias stage) has run once (success). `workflow_dispatch` still needs the file on the default branch; before merging use a push whose commit message contains `[bias-check]`.
- End-to-end data download + backtest (blocked here by network policy).
- Fee + slippage assumption of 0.15 % per side.

## Open decisions for the owner

1. Data/backtest location: GitHub Actions (free) and/or allow-list one exchange host in Claude Code Cloud.
2. Disable the upstream workflows listed above (recommended).
3. Exchange for Phase 3 research data: OKX is the working default (see reachability table); Kraken/KuCoin/Gate are alternatives. Binance only via a different host.

## Change log

- 2026-11-26 — S7: risk layer V3 (synthetic), gate methodology audit, family design review (NO-GO), production roadmap, amendment A10; no strategy, no market evaluation.
- 2026-11-26 — S6: feasibility gate + benchmark infrastructure (synthetic), stale-position review, design-only next-family proposal, amendment A9; no market evaluation.
- 2026-11-26 — S5-infra: S4 freeze, investigations, loader/guard/budget (synthetic), amendment A8; original S5 not executed.
- 2026-11-26 — S4: point-in-time dataset builder and dataset (GO, research only), licensing alternatives (documentation), amendment A7.
- 2026-11-26 — S2 frozen (freeze record); S3 data feasibility gate: audit scripts, `quantlab/data_audit.py` (+15 tests), licensing findings, integration plan (design), ledger amendment A6. CONDITIONAL GO for data; no market evaluation.
- 2026-11-25 — Family A evaluated (one run): not credible, fails T1/T3/T4/T7; liquidity amendment A1, ledger amendment A2.
- 2026-11-25 — Family A implemented and frozen (spec v5), synthetic tests and causality validation; no market evaluation.
- 2026-11-25 — Phase 4B Stage 0: execution engine, causality tests, statistical rules, ledger, manifest v4 (no strategy, no holdout).
- 2026-11-25 — Phase 4: R1 risk overlay research (protocol v3, 2 research runs, run 1 invalid); R1 rejected on research data; holdout untouched.
- 2026-11-24 — Phase 1: audit, `AGENTS.md`, `ROADMAP.md`, journal, `quant/` layout, safety policy, configs, scripts, Quant CI.
- 2026-11-25 — fix: `quant/__init__.py` (mypy duplicate-module failure introduced by us).
- 2026-11-25 — final audit: environment-variable bypass closed (+8 tests), Phase 2 acceptance criteria D1–D7,
  residual-risk and CI documentation.
- 2026-11-25 — Phase 2 (approved): strategy specs, 5 strategies, `quant_common`, `strategy_policy`, 78 new tests,
  Phase 3 threshold proposal, `quant-research.yml` (bias stage), always-on informational network probe.
- 2026-11-27 — S8: pre-registered design study (synthetic), methodology review, data/licensing verification attempt (unverified), V3 adoption review, decision framework: NO-GO under the pre-registered rule; no strategy, no market evaluation.
