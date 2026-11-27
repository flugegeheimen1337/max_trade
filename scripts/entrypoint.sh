#!/bin/sh
# Run the lab preflight, then hand control to the Freqtrade image entrypoint.
set -eu

CONFIG="${LAB_CONFIG:-/freqtrade/user_data/config.active.json}"
STRATEGY="${LAB_STRATEGY:-/freqtrade/user_data/strategies/BaselineTrendStrategy.py}"

if [ ! -f "$CONFIG" ]; then
  echo "lab: missing $CONFIG. From the repository root run: ./scripts/lab.sh init" >&2
  exit 1
fi

MODE=safety
if [ "${1:-}" = "trade" ]; then
  MODE=trade
fi

mkdir -p \
  /freqtrade/user_data/logs \
  /freqtrade/user_data/data \
  /freqtrade/user_data/backtest_results

python3 -m core.preflight --config "$CONFIG" --strategy "$STRATEGY" --mode "$MODE"
exec freqtrade "$@"
