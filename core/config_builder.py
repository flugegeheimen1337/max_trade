"""Build the Freqtrade config that the container is allowed to start."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.constants import (
    ALLOWED_EXCHANGES,
    DEFAULT_EXCHANGE,
    ALLOWED_PAIRS,
    API_CONTAINER_PORT,
    API_LISTEN,
    DOWNLOAD_TIMERANGE,
    DRY_RUN_WALLET,
    FEE,
    MAX_OPEN_TRADES,
    STAKE_AMOUNT,
    STRATEGY_NAME,
    TRADING_TIMEFRAME,
    VERIFY_TIMERANGE,
)
from core.envfile import load_env_file

TIMERANGE_PATTERN_ERROR = "Timerange must look like 20200101- or 20240101-20240301."


@dataclass(frozen=True)
class LabSettings:
    exchange: str
    api_username: str
    api_password: str
    jwt_secret_key: str
    ws_token: str
    api_port: int
    download_timerange: str
    verify_timerange: str

    @classmethod
    def from_mapping(cls, raw: dict[str, str]) -> "LabSettings":
        exchange = raw.get("EXCHANGE", DEFAULT_EXCHANGE).strip().lower()
        if exchange not in ALLOWED_EXCHANGES:
            allowed = ", ".join(sorted(ALLOWED_EXCHANGES))
            raise ValueError(f"EXCHANGE must be one of: {allowed}.")
        username = raw.get("API_USERNAME", "freqtrade").strip()
        if not username or any(char.isspace() for char in username):
            raise ValueError("API_USERNAME must be a single non-empty word.")
        return cls(
            exchange=exchange,
            api_username=username,
            api_password=raw.get("API_PASSWORD", ""),
            jwt_secret_key=raw.get("JWT_SECRET_KEY", ""),
            ws_token=raw.get("WS_TOKEN", ""),
            api_port=_port(raw.get("API_PORT", "8080")),
            download_timerange=_timerange(raw.get("DOWNLOAD_TIMERANGE", DOWNLOAD_TIMERANGE)),
            verify_timerange=_timerange(raw.get("VERIFY_TIMERANGE", VERIFY_TIMERANGE)),
        )

    @classmethod
    def from_env_file(cls, path: Path) -> "LabSettings":
        return cls.from_mapping(load_env_file(path))


def load_base_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def render_config(base: dict[str, Any], settings: LabSettings) -> dict[str, Any]:
    """Return a spot dry-run config. Live trading fields are cleared here."""
    config = json.loads(json.dumps(base))
    config["max_open_trades"] = MAX_OPEN_TRADES
    config["stake_currency"] = "USDT"
    config["stake_amount"] = STAKE_AMOUNT
    config["tradable_balance_ratio"] = 0.99
    config["fiat_display_currency"] = "USD"
    config["timeframe"] = TRADING_TIMEFRAME
    config["dry_run"] = True
    config["dry_run_wallet"] = DRY_RUN_WALLET
    config["fee"] = FEE
    config["cancel_open_orders_on_exit"] = False
    config["trading_mode"] = "spot"
    config["margin_mode"] = ""
    config["initial_state"] = "stopped"
    config["force_entry_enable"] = False
    config["strategy"] = STRATEGY_NAME
    config["bot_name"] = "lab-baseline"
    config["db_url"] = "sqlite:////freqtrade/user_data/tradesv3.dryrun.sqlite"

    exchange = dict(config.get("exchange") or {})
    for secret_field in (
        "api_key",
        "key",
        "secret",
        "password",
        "uid",
        "account_id",
        "wallet_address",
        "private_key",
    ):
        exchange.pop(secret_field, None)
    exchange["name"] = settings.exchange
    exchange["api_key"] = ""
    exchange["secret"] = ""
    exchange["pair_whitelist"] = list(ALLOWED_PAIRS)
    exchange["pair_blacklist"] = []
    exchange["ccxt_config"] = {"enableRateLimit": True}
    exchange["ccxt_async_config"] = {"enableRateLimit": True}
    config["exchange"] = exchange

    config["pairlists"] = [{"method": "StaticPairList"}]
    config["telegram"] = {"enabled": False, "token": "", "chat_id": ""}
    config["api_server"] = {
        "enabled": True,
        "listen_ip_address": API_LISTEN,
        "listen_port": API_CONTAINER_PORT,
        "verbosity": "error",
        "enable_openapi": False,
        "jwt_secret_key": settings.jwt_secret_key,
        "ws_token": settings.ws_token,
        "CORS_origins": [],
        "username": settings.api_username,
        "password": settings.api_password,
    }
    return config


def write_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        return


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise ValueError("API_PORT must be an integer.") from exc
    if port < 1024 or port > 65535:
        raise ValueError("API_PORT must be between 1024 and 65535.")
    return port


def _timerange(value: str) -> str:
    text = value.strip()
    parts = text.split("-")
    if len(parts) != 2 or len(parts[0]) != 8 or not parts[0].isdigit():
        raise ValueError(TIMERANGE_PATTERN_ERROR)
    if parts[1] and (len(parts[1]) != 8 or not parts[1].isdigit()):
        raise ValueError(TIMERANGE_PATTERN_ERROR)
    return text
