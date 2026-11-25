# AGENTS.md — rules for AI agents and contributors

This repository is a **fork of Freqtrade** (GPL-3.0) used as the base of a research-driven,
spot-only crypto trading research system. Read `PROJECT_STATUS.md` first, then `ROADMAP.md`.

## Hard rules (never break, never "temporarily" relax)

1. **No real money.** `dry_run` must always be `true`. Never enable live trading, never add
   code paths that place real orders. The safety policy (`quant/quantlab/safety.py`) enforces
   this in CI; do not weaken it without explicit written owner approval in `PROJECT_STATUS.md`.
2. **Spot only.** No futures, margin, leverage, shorting, martingale or unbounded position
   averaging (`position_adjustment_enable` stays `false` until a bounded policy is approved).
3. **No credentials.** Never request, store, log or commit exchange API keys, Telegram tokens,
   passwords or webhook URLs. Config credential fields stay empty; runtime secrets (later
   phases only) come from environment variables / GitHub encrypted secrets.
4. **No fabricated results.** Every performance number must come from a command that was
   actually run, with the command, commit, data range and config recorded in the research
   journal. Label anything not measured as an *assumption* or *hypothesis*.
5. **No auto-merge, no deploy.** Work on a feature branch, open **draft** PRs only. The owner
   merges. Never push to `develop` or `stable`.
6. **No paid services** (APIs, servers, data feeds) without explicit owner approval.
7. **Tests before "done".** Run `bash quant/scripts/check.sh` and report the real output.

## Repository layout

| Path | Owner | Notes |
|---|---|---|
| `freqtrade/`, `tests/`, `docs/`, `ft_client/`, root build files | upstream | **Do not modify.** Keeps upstream sync conflict-free. |
| `.github/workflows/ci.yml` | upstream, **one fork patch** | Codecov upload step skipped unless `github.repository == 'freqtrade/freqtrade'` (needs a secret the fork must not have). Marked `FORK PATCH`; re-apply after upstream syncs. All upstream tests still run. |
| `.github/workflows/quant-*.yml` | project | Our CI (`quant-ci.yml`) and bias checks (`quant-bias-check.yml`). Upstream workflows are left untouched. |
| `quant/` | project | All project code, configs, research and docs. |
| `quant/quantlab/` | project | Python package: safety policy, (later) metrics, validation, risk, reporting. |
| `quant/strategies/` | project | Freqtrade strategy classes (`--strategy-path quant/strategies`) + `quant_common.py`. Every strategy must pass `quantlab.strategy_policy` (checked by `check.sh`). Specs live in `quant/docs/strategies/` and are written **before** the code runs on data. |
| `quant/configs/` | project | Layered configs, no secrets. Do not name files `config*.json` (gitignored upstream). |
| `quant/journal/` | project | Research journal, one dated file per study. |
| `quant/docs/` | project | Audit, architecture and research notes. |
| `AGENTS.md`, `ROADMAP.md`, `PROJECT_STATUS.md` | project | Keep current at the end of every task. |

`user_data/` is gitignored upstream; use it only for local, disposable data and results.

## Workflow

```bash
bash quant/scripts/setup_env.sh     # reproducible env (uv + pinned upstream deps)
bash quant/scripts/check.sh         # lint + tests + safety policy (the quality gate)
```

- One branch and one draft PR per task. Small, reviewable diffs.
- Update `PROJECT_STATUS.md` (what changed, verified vs. assumed) at the end of each task.
- Research tasks add a journal entry using `quant/journal/TEMPLATE.md`.
- Prefer Freqtrade built-ins (backtesting, lookahead/recursive analysis, protections) over
  re-implementing them. Add dependencies only when clearly justified.
- Code and technical docs in English. The owner communicates in Croatian.

## Research standards

- Simple, explainable strategies first; ML only after a validated baseline (Phase 6).
- Every strategy is compared against buy-and-hold on the same pairs and period.
- Mandatory: fees + slippage buffer, out-of-sample split, walk-forward validation,
  `lookahead-analysis` and `recursive-analysis` clean, results across bull/bear/sideways.
- Reject strategies that only work in-sample or depend on a narrow parameter choice.
