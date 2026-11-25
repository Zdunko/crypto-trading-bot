# 2026-11-25 - Phase 4B: integrity findings and protocol v4 design (no runs)

Analysis only (code reading, recorded run results, web check of bibliographic data). No backtest, no strategy code, no CI run.
Findings and the proposed protocol: `quant/docs/phase4b/research_protocol_proposal.md`.
Correction recorded: the Phase 4 report said the breaker only observed equity at entry decisions; it also ran in `custom_stoploss`
every candle with open positions. The likelier cause of "no halt at 21.8 % drawdown" is the different cost world seen by the breaker.
