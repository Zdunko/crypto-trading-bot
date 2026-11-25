# 2026-11-25 — Phase 3 start: data validation, protocol v2 freeze, bias-check expansion

- **Owner instructions (2026-11-25):** Phase 2 conditionally approved; OKX approved; T1 ≥ 200 trades, T4 ≤ 20 %
  (and ≤ benchmark), T5 ≥ 1.3, rest unchanged; explicit fee + slippage without double counting; untouched
  holdout; wider bias checks; report uncertainty/sample limits/survivorship; never optimise on the holdout;
  fix the Codecov failure without disabling upstream tests, no paid services, no secrets.

## Upstream Codecov failure (investigated)
- Run 45554153646: 15 jobs succeeded (Ubuntu 22.04/24.04/26.04, ARM, macOS-26, Windows 2022/2025, docs, mypy,
  pre-commit, the online exchange tests); 5024 tests passed on 3.14. The only failing step was the Codecov upload
  (`Token required - not valid tokenless upload`: the fork has no `CODECOV_TOKEN` and the step has
  `fail_ci_if_error: true`); matrix `fail-fast` then cancelled 7 jobs.
- Fix: one condition on the upload step (`github.repository == 'freqtrade/freqtrade'`, marked `FORK PATCH`).
  Tests still run with coverage; no secret and no paid service added. Result of the first full run is recorded in
  PROJECT_STATUS.md.

## Data (verified from the workflow log, run 45558871512, commit 331ab62)
- OKX spot 1h, 8 pairs, 2020-01-01 → 2026-11-25 (exclusive). 60 480 candles per pair (SOL 53 918, listed
  2020-09-30), **0 missing, 0 gaps, 0 duplicates, 0 impossible OHLC**; zero-volume candles ≤ 0.57 % (DOGE); one DOGE
  hourly move above 50 % flagged (warning). Dataset sha256 `fd94dcb6…8085`.

## Protocol v2 (frozen in this commit)
- Evaluation 2021-01-01 → 2025-07-01 (nine 6-month windows), holdout 2025-07-01 → 2026-11-25. Both fixed from data
  availability and calendar boundaries **before any return was computed**.
- Costs: Freqtrade `--fee` 0.10 % (base) / 0.20 % (stress); slippage 0.05 % / 0.10 % (+ equal extra on stop exits)
  applied afterwards; double-counting guard in code and test. See `docs/strategies/phase3_validation_thresholds.md`.
- Freeze mechanics: `protocol/frozen_manifest.json` + `python -m quantlab.protocol verify` in `check.sh` and in
  every research stage.

## Research run log (every run, including reruns)
| Stage | Run | Commit | Purpose / outcome |
|---|---|---|---|
| data | 45558871512 | 331ab62 | download + validation: passed (see above) |
