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

if [ "${LAB_MODE:-}" = "futures_research" ]; then
  case "${1:-}" in
    download-data|backtesting|lookahead-analysis|recursive-analysis|list-data) ;;
    *)
      echo "lab: futures research allows data and backtest commands only, not '${1:-}'." >&2
      exit 1
      ;;
  esac
  MODE=futures_research
fi

mkdir -p \
  /freqtrade/user_data/logs \
  /freqtrade/user_data/data \
  /freqtrade/user_data/backtest_results

python3 -m core.preflight --config "$CONFIG" --strategy "$STRATEGY" --mode "$MODE"
exec freqtrade "$@"
