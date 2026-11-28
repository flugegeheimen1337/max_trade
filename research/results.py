"""Summarise one Freqtrade futures backtest archive without re-simulating trades."""

from __future__ import annotations

import json
import math
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_strategy_result(path: Path) -> tuple[str, dict[str, Any]]:
    with zipfile.ZipFile(path) as archive:
        names = [
            name for name in archive.namelist()
            if name.endswith(".json") and not name.endswith("_config.json")
        ]
        if len(names) != 1:
            raise ValueError(f"{path.name} does not contain one backtest report.")
        payload = json.loads(archive.read(names[0]))
    strategies = payload.get("strategy") or {}
    if len(strategies) != 1:
        raise ValueError(f"{path.name} must hold exactly one strategy.")
    return next(iter(strategies.items()))


def _profit_factor(profits: list[float]) -> float | None:
    gains = sum(p for p in profits if p > 0)
    losses = -sum(p for p in profits if p < 0)
    if losses == 0:
        return None if gains == 0 else math.inf
    return gains / losses


def _side(trades: list[dict[str, Any]]) -> dict[str, Any]:
    profits = [float(t.get("profit_abs") or 0.0) for t in trades]
    wins = sum(1 for p in profits if p > 0)
    return {
        "trades": len(trades),
        "profit_abs": round(sum(profits), 4),
        "profit_factor": _round(_profit_factor(profits)),
        "win_rate": round(wins / len(trades), 4) if trades else None,
    }


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None or math.isinf(value):
        return value
    return round(value, digits)


def _fees(trade: dict[str, Any]) -> float:
    amount = float(trade.get("amount") or 0.0)
    open_cost = amount * float(trade.get("open_rate") or 0.0) * float(trade.get("fee_open") or 0.0)
    close_cost = amount * float(trade.get("close_rate") or 0.0) * float(trade.get("fee_close") or 0.0)
    return open_cost + close_cost


def summarise(result: dict[str, Any], starting_balance: float) -> dict[str, Any]:
    trades = result.get("trades") or []
    longs = [t for t in trades if not t.get("is_short")]
    shorts = [t for t in trades if t.get("is_short")]
    profits = [float(t.get("profit_abs") or 0.0) for t in trades]
    monthly: dict[str, float] = defaultdict(float)
    by_pair: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_tag: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        monthly[str(trade.get("close_date", ""))[:7]] += float(trade.get("profit_abs") or 0.0)
        by_pair[str(trade.get("pair"))].append(trade)
        by_tag[str(trade.get("enter_tag") or "")].append(trade)
    monthly_returns = [value / starting_balance for value in monthly.values()]
    net = sum(profits)
    top_share = None
    if net > 0:
        top_share = sum(sorted(profits, reverse=True)[:3]) / net
    return {
        "trades": len(trades),
        "net_profit_abs": round(net, 4),
        "total_return": round(net / starting_balance, 6),
        "profit_factor": _round(_profit_factor(profits)),
        "win_rate": round(sum(1 for p in profits if p > 0) / len(trades), 4) if trades else None,
        "max_drawdown_account": _round(result.get("max_drawdown_account")),
        "sharpe": _round(result.get("sharpe")),
        "sortino": _round(result.get("sortino")),
        "calmar": _round(result.get("calmar")),
        "mean_monthly_return": round(sum(monthly_returns) / len(monthly_returns), 6) if monthly_returns else None,
        "worst_month": round(min(monthly_returns), 6) if monthly_returns else None,
        "profitable_months": (
            round(sum(1 for r in monthly_returns if r > 0) / len(monthly_returns), 4)
            if monthly_returns else None
        ),
        "fees_abs": round(sum(_fees(t) for t in trades), 4),
        "funding_abs": round(sum(float(t.get("funding_fees") or 0.0) for t in trades), 4),
        "liquidations": sum(1 for t in trades if t.get("exit_reason") == "liquidation"),
        "stop_losses": sum(1 for t in trades if t.get("exit_reason") == "stop_loss"),
        "top3_share_of_profit": _round(top_share),
        "long": _side(longs),
        "short": _side(shorts),
        "by_pair": {pair: _side(rows) for pair, rows in sorted(by_pair.items())},
        "by_tag": {tag: _side(rows) for tag, rows in sorted(by_tag.items())},
        "backtest_days": result.get("backtest_days"),
        "market_change": _round(result.get("market_change")),
    }
