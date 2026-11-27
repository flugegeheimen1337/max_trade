"""Stage-1 limits for the research lab.

These values are the engine probe, not optimized trading parameters.
"""

from __future__ import annotations

FREQTRADE_IMAGE = "freqtradeorg/freqtrade:2026.10"
FREQTRADE_RELEASE = "2026.10"
STRATEGY_NAME = "BaselineTrendStrategy"
INTERFACE_VERSION = 3

DEFAULT_EXCHANGE = "bybit"
FALLBACK_EXCHANGE = "okx"
# Binance stays available as a public candle source. It is not the operating venue.
ALLOWED_EXCHANGES = frozenset({DEFAULT_EXCHANGE, FALLBACK_EXCHANGE, "binance"})
ALLOWED_PAIRS = ("BTC/USDT", "ETH/USDT")
TIMEFRAMES = ("15m", "1h", "4h", "1d")
TRADING_TIMEFRAME = "15m"

DRY_RUN_WALLET = 1000
STAKE_AMOUNT = 100
MAX_OPEN_TRADES = 2
# Explicit fee assumption for comparable runs. 0.001 = 0.1% per side.
FEE = 0.001

DOWNLOAD_TIMERANGE = "20200101-"
VERIFY_TIMERANGE = "20240101-20240301"

API_LISTEN = "127.0.0.1"
API_CONTAINER_PORT = 8080

PLACEHOLDER_SECRETS = frozenset(
    {
        "",
        "change-me-local-only-password",
        "change-me-local-only-jwt-secret-key-32",
        "change-me-local-only-ws-token-32chars",
    }
)

MIN_SECRET_LENGTH = 32

DISCLAIMER = (
    "A repeated backtest shows that the engine produced the same result twice. "
    "It is not evidence that the strategy is profitable."
)
