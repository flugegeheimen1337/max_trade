"""Refuse a Freqtrade config that could leave spot dry-run."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from core.constants import (
    ALLOWED_EXCHANGES,
    ALLOWED_PAIRS,
    API_LISTEN,
    DRY_RUN_WALLET,
    FEE,
    MAX_OPEN_TRADES,
    MIN_SECRET_LENGTH,
    PLACEHOLDER_SECRETS,
    STAKE_AMOUNT,
    TRADING_TIMEFRAME,
)

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


def safety_problems(config: dict[str, Any], strategy_text: str) -> list[str]:
    problems: list[str] = []
    if config.get("dry_run") is not True:
        problems.append("dry_run must be true. Live trading is blocked in this build.")
    if config.get("trading_mode") != "spot":
        problems.append("trading_mode must be spot.")
    if config.get("margin_mode") not in ("", None):
        problems.append("margin_mode must be empty for spot.")
    if config.get("stake_currency") != "USDT":
        problems.append("stake_currency must be USDT.")
    if config.get("dry_run_wallet") != DRY_RUN_WALLET:
        problems.append(f"dry_run_wallet must be {DRY_RUN_WALLET}.")
    if config.get("stake_amount") != STAKE_AMOUNT:
        problems.append(f"stake_amount must be {STAKE_AMOUNT} for the stage-1 probe.")
    if config.get("max_open_trades") != MAX_OPEN_TRADES:
        problems.append(f"max_open_trades must be {MAX_OPEN_TRADES}.")
    if config.get("timeframe") != TRADING_TIMEFRAME:
        problems.append(f"timeframe must be {TRADING_TIMEFRAME}.")
    if config.get("fee") != FEE:
        problems.append(f"fee must be {FEE}.")
    if config.get("force_entry_enable") is True:
        problems.append("force_entry_enable must stay false.")
    if config.get("initial_state") != "stopped":
        problems.append("initial_state must be stopped until the operator starts dry-run.")

    exchange = config.get("exchange")
    if not isinstance(exchange, dict):
        problems.append("exchange config is missing.")
    else:
        name = str(exchange.get("name", "")).lower()
        if name not in ALLOWED_EXCHANGES:
            problems.append("exchange must be binance, okx, or bybit.")
        for field in SECRET_FIELDS:
            value = exchange.get(field)
            if value not in (None, ""):
                problems.append(f"exchange.{field} must be empty. Public data does not use keys.")
        whitelist = exchange.get("pair_whitelist")
        if tuple(whitelist or ()) != ALLOWED_PAIRS:
            problems.append("pair whitelist must be exactly BTC/USDT and ETH/USDT.")

    pairlists = config.get("pairlists")
    if pairlists != [{"method": "StaticPairList"}]:
        problems.append("pairlists must be StaticPairList.")

    telegram = config.get("telegram") or {}
    if telegram.get("enabled") is True or telegram.get("token") or telegram.get("chat_id"):
        problems.append("telegram must stay disabled in this build.")

    api = config.get("api_server") or {}
    if api.get("listen_ip_address") != API_LISTEN:
        problems.append("api_server.listen_ip_address must be 127.0.0.1.")
    origins = api.get("CORS_origins")
    if origins not in ([], None):
        problems.append("api_server.CORS_origins must be empty.")

    problems.extend(strategy_problems(strategy_text))
    return problems


def trade_problems(config: dict[str, Any]) -> list[str]:
    api = config.get("api_server") or {}
    problems: list[str] = []
    password = str(api.get("password") or "")
    jwt_secret = str(api.get("jwt_secret_key") or "")
    ws_token = str(api.get("ws_token") or "")
    if password in PLACEHOLDER_SECRETS:
        problems.append("API password is still a placeholder. Run lab init on the PC.")
    if jwt_secret in PLACEHOLDER_SECRETS or len(jwt_secret) < MIN_SECRET_LENGTH:
        problems.append("JWT secret must be a generated value of at least 32 characters.")
    if ws_token in PLACEHOLDER_SECRETS or len(ws_token) < MIN_SECRET_LENGTH:
        problems.append("WebSocket token must be a generated value of at least 32 characters.")
    return problems


def strategy_problems(strategy_text: str) -> list[str]:
    problems: list[str] = []
    if re.search(r"(?m)^\s*can_short\s*(:\s*bool)?\s*=\s*True\b", strategy_text):
        problems.append("strategy sets can_short = True.")
    if "enter_short" in strategy_text:
        problems.append("strategy references short entries.")
    if re.search(r"position_adjustment_enable\s*(:\s*bool)?\s*=\s*True\b", strategy_text):
        problems.append("position adjustment must stay disabled.")
    return problems


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(config: dict[str, Any], strategy_text: str, mode: str) -> list[str]:
    problems = safety_problems(config, strategy_text)
    if mode == "trade":
        problems.extend(trade_problems(config))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Block live-trading Freqtrade configs.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--strategy", required=True, type=Path)
    parser.add_argument("--mode", choices=("safety", "trade"), default="safety")
    args = parser.parse_args(argv)
    problems = evaluate(load_config(args.config), args.strategy.read_text(encoding="utf-8"), args.mode)
    if problems:
        print("preflight failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    print(f"preflight passed ({args.mode}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
