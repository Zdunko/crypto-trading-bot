# PROJECT STATUS

_Last updated: 2026-11-24 · Phase 1 complete, **awaiting owner approval** for Phase 2._

## Current state

| Item | State |
|---|---|
| Phase | 1 — Repository audit & foundation (done) |
| Branch | `claude/freqtrade-trading-system-b82aek` (draft PR, not merged) |
| Real-money trading | **Disabled by policy** (enforced in CI) |
| Exchange credentials | None requested, none stored |
| Strategies | None yet (Phase 2) |
| Backtest results | **None** — no market data downloaded, no performance claims exist |
| Monthly cost | €0 |

## Verified results (commands actually run in Claude Code Cloud)

- `bash quant/scripts/check.sh` → ruff clean, **38 passed**, safety policy OK.
- Upstream suite `pytest -n 4 --timeout=60 --ignore=tests/exchange_online --ignore=tests/freqai`
  → **4807 passed, 20 skipped, 6 failed** (the `quant/` collection error seen in that run is fixed
  by `quant/conftest.py`). All 6 failures are environment-related, not code defects:
  - 2× FreqAI model listing — optional FreqAI deps intentionally not installed;
  - 2× `pip-audit` — dev tool not installed;
  - 1× file-permission test — container runs as root;
  - 1× invalid-URL websocket test — times out under the sandbox network proxy.
- `zizmor` audit of `.github/workflows/quant-ci.yml` → no findings.
- Network: exchange APIs unreachable from Claude Code Cloud; backtesting fails at
  `reload_markets` without exchange access.

## Not yet verified (assumptions)

- `quant-ci.yml` passing on GitHub Actions (first run happens after push; Actions may need to be
  enabled on the fork by the owner).
- Which exchange data APIs are reachable from GitHub runners (run the workflow manually with
  `network_probe: true`).
- Fee + slippage assumption of 0.15 % per side.

## Open decisions for the owner

1. **Data/backtest location:** GitHub Actions (default, free) and/or allow-list one exchange host
   (e.g. `api.binance.com`, `data.binance.vision`) in this Claude Code environment.
2. **Upstream CI:** disable upstream Freqtrade workflows in the GitHub Actions UI to avoid a
   15-job matrix on every draft PR (recommended), or keep them.
3. **Exchange for research data:** Binance (deepest history/liquidity, may be geo-blocked from
   US runners) vs. alternative — decided after the network probe.

## Change log

- 2026-11-24 — Phase 1: audit (`quant/docs/phase1-audit.md`), `AGENTS.md`, `ROADMAP.md`,
  research journal, `quant/` layout, safety policy + tests, configs, env/check scripts, Quant CI.
