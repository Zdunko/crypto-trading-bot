# quant/ — project code on top of Freqtrade

Everything project-specific lives here so the upstream Freqtrade source stays untouched and
easy to sync. Rules: see `../AGENTS.md`. Plan: `../ROADMAP.md`. State: `../PROJECT_STATUS.md`.

```
quant/
├── configs/        layered Freqtrade configs (no secrets): base.json + backtest.json (+ dryrun later)
├── strategies/     4 strategies + BuyAndHold benchmark + quant_common.py (regime, ATR sizing)
├── quantlab/       python package: safety (configs) + strategy_policy (strategy source); later: metrics, validation, risk, reports
├── tests/          pytest suite for quantlab and strategies
├── scripts/        setup_env.sh (reproducible env), check.sh (quality gate)
├── journal/        research journal, one dated entry per study
└── docs/           audit, architecture and research notes
```

## Data flow (target architecture)

```
exchange public API ──download-data──▶ OHLCV (feather, not in git, hash recorded)
                                            │
quant/strategies + configs ──backtesting──▶ Freqtrade result JSON
                                            │
quantlab.metrics / validation ─────────────▶ walk-forward + benchmark report (Markdown/HTML)
                                            │
                                   journal entry + PR (owner review)
```

## Config layering

```bash
freqtrade backtesting -c quant/configs/base.json -c quant/configs/backtest.json \
  --strategy-path quant/strategies --strategy <Name>
```

`base.json`: spot, dry-run wallet 1000 USDT, max 3 open trades, static pair list.
`backtest.json`: exchange taker fee 0.10 % per side (assumption). Slippage is **not** in this number: it is
applied afterwards by `quantlab.costs` so costs are counted exactly once (see `protocol/protocol.json`).
