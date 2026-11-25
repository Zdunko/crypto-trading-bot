#!/usr/bin/env bash
# Download PUBLIC candles (no credentials) for the universe in configs/base.json and validate them.
# Exit code != 0 when validation fails or the dataset hash differs from EXPECT_DATA_HASH.
set -euo pipefail
cd "$(dirname "$0")/../.."

EXCHANGE="${EXCHANGE:-okx}"
DATA_START="${DATA_START:-20200101}"   # inclusive, UTC
DATA_END="${DATA_END:-20261125}"       # exclusive, UTC (last candle 2026-11-24 23:00)
export FREQTRADE__EXCHANGE__NAME="$EXCHANGE"

freqtrade create-userdir --userdir user_data >/dev/null
freqtrade download-data -c quant/configs/base.json --userdir user_data -t 1h \
  --timerange "${DATA_START}-${DATA_END}"

expect=()
[ -n "${EXPECT_DATA_HASH:-}" ] && expect=(--expect-hash "$EXPECT_DATA_HASH")
(cd quant && python -m quantlab.data_validation --datadir "../user_data/data/$EXCHANGE" \
  --config configs/base.json \
  --start "${DATA_START:0:4}-${DATA_START:4:2}-${DATA_START:6:2}" \
  --end "${DATA_END:0:4}-${DATA_END:4:2}-${DATA_END:6:2}" \
  --json-out ../user_data/data_report.json "${expect[@]}")
