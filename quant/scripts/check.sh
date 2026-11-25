#!/usr/bin/env bash
# Single quality gate for project code. Must pass before a task is marked complete.
set -euo pipefail
cd "$(dirname "$0")/../.."
# shellcheck disable=SC1091
[ -z "${VIRTUAL_ENV:-}" ] && [ -f .venv/bin/activate ] && source .venv/bin/activate

echo "== ruff lint";    ruff check quant
echo "== ruff format";  ruff format --check quant
echo "== pytest";       (cd quant && python -m pytest -q)
echo "== safety policy"
(cd quant && python -m quantlab.safety configs/base.json configs/backtest.json)
echo "== frozen protocol"
(cd quant && python -m quantlab.protocol verify4)
echo "== strategy policy"
(cd quant && python -m quantlab.strategy_policy strategies strategies_r1)
echo "== all checks passed"
