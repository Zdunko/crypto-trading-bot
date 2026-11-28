# 2026-11-24 — Phase 1: repository audit & foundation

- **Question:** What does the repository contain, what can run where, and what is the safest
  foundation for spot-only, research-driven strategy development?
- **Commit:** base `7fcb509` (Freqtrade 2026.11-dev) · **Branch:** `claude/freqtrade-trading-system-b82aek`
- **Data:** none (no market data downloaded in this phase)

## Results (verified)

- Repository = public fork of `freqtrade/freqtrade`, unmodified upstream source.
- Env: Python 3.13.18, deps installed from upstream pins with `uv` in seconds.
- `quant` quality gate (`bash quant/scripts/check.sh`): ruff clean, 38 tests passed, safety policy OK.
- Upstream test suite (`pytest -n 4`, excluding `tests/exchange_online`, `tests/freqai`):
  see PROJECT_STATUS.md for the exact counts.
- Claude Code Cloud network: PyPI reachable; Binance, Binance Vision, Kraken, OKX, Bybit,
  Coinbase, KuCoin, Gate all unreachable (proxy refusal). Backtesting with local test data
  fails at `reload_markets` → backtests cannot run here without an allow-listed exchange host.

## Interpretation

- Research compute should run in GitHub Actions (free for public repos) with artifacts, or in
  Claude Code after the owner allow-lists one exchange host.
- Freqtrade covers backtesting, bias analysis, protections and dry-run well; we must add
  slippage handling, walk-forward validation, benchmark comparison and portfolio risk guards.

## Assumptions & limitations

- GitHub Actions reachability of exchange APIs is not yet verified (probe job prepared).
- Fee/slippage assumption (0.15 % per side) is not yet calibrated.

## Decision / next step

Owner approval of Phase 1, then Phase 2 (strategy specs) starting with the data-source decision.
