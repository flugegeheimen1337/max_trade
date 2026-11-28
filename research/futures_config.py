"""Render Freqtrade configs for futures backtests. These configs never trade."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SECRET_FIELDS = (
    "api_key",
    "key",
    "secret",
    "password",
    "uid",
    "account_id",
    "wallet_address",
    "private_key",
)
MAX_RESEARCH_LEVERAGE = 10.0


def render_futures_config(
    base: dict[str, Any],
    *,
    exchange: str,
    pairs: list[str],
    timeframe: str,
    leverage: float,
    notional_per_trade: float,
    price_stop: float,
    fee: float,
    max_open_trades: int,
    wallet: float,
) -> dict[str, Any]:
    if not 1.0 <= leverage <= MAX_RESEARCH_LEVERAGE:
        raise ValueError(f"Research leverage must be between 1 and {MAX_RESEARCH_LEVERAGE:g}.")
    if not 0.0 < price_stop < 1.0 / leverage:
        raise ValueError("The price stop must sit before the isolated liquidation distance.")
    config = json.loads(json.dumps(base))
    config["dry_run"] = True
    config["dry_run_wallet"] = wallet
    config["trading_mode"] = "futures"
    config["margin_mode"] = "isolated"
    config["timeframe"] = timeframe
    config["fee"] = fee
    config["max_open_trades"] = max_open_trades
    # Same notional at every leverage: the margin shrinks instead of the position growing.
    config["stake_amount"] = round(notional_per_trade / leverage, 8)
    # Freqtrade measures the futures stop on margin, so scale it to keep one price distance.
    config["stoploss"] = -round(price_stop * leverage, 8)
    config["lab_leverage"] = leverage
    config["force_entry_enable"] = False
    config["initial_state"] = "stopped"
    config["telegram"] = {"enabled": False, "token": "", "chat_id": ""}
    config.pop("api_server", None)
    exchange_config = dict(config.get("exchange") or {})
    for field in SECRET_FIELDS:
        exchange_config.pop(field, None)
    exchange_config["name"] = exchange
    exchange_config["api_key"] = ""
    exchange_config["secret"] = ""
    exchange_config["pair_whitelist"] = list(pairs)
    exchange_config["pair_blacklist"] = []
    config["exchange"] = exchange_config
    config["pairlists"] = [{"method": "StaticPairList"}]
    return config


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
