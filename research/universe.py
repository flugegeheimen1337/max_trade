"""Check which candidate USDT-M perpetuals exist and rank them by liquidity.

This is a snapshot of today's market. It must not be used to pick coins for a
historical period: that would add survivorship bias. Backtests on this list are
labelled LIMITED_VALIDATION for that reason.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DAY_MS = 86_400_000


@dataclass
class Instrument:
    base: str
    tier: str
    symbol: str
    listed: bool = False
    status: str = ""
    launch_date: str = ""
    listing_age_days: float = 0.0
    delivery_time: str = ""
    contract_size: float | None = None
    tick_size: float | None = None
    lot_step: float | None = None
    min_qty: float | None = None
    min_notional: float | None = None
    max_leverage: float | None = None
    funding_interval_min: int | None = None
    avg_daily_turnover_usdt: float | None = None
    turnover_24h_usdt: float | None = None
    open_interest_usdt: float | None = None
    spread_bps: float | None = None
    funding_rate: float | None = None
    annualized_volatility: float | None = None
    category: str = "BLOCKED"
    reasons: list[str] = field(default_factory=list)


def classify(item: Instrument, filters: dict[str, float]) -> Instrument:
    reasons: list[str] = []
    if not item.listed:
        reasons.append("no USDT-M perpetual on the exchange")
    else:
        if item.status != "Trading":
            reasons.append(f"status {item.status or 'unknown'}")
        if item.delivery_time not in ("", "0"):
            reasons.append("delisting or delivery is scheduled")
        if item.listing_age_days < filters["min_listing_age_days"]:
            reasons.append(f"listed {item.listing_age_days:.0f} days ago")
        turnover = item.avg_daily_turnover_usdt or 0.0
        if turnover < filters["min_avg_daily_turnover_usdt"]:
            reasons.append(f"30d average turnover {turnover / 1e6:.1f}M USDT")
    if reasons:
        item.category = "BLOCKED"
        item.reasons = reasons
        return item

    research_only: list[str] = []
    if (item.open_interest_usdt or 0.0) < filters["min_open_interest_usdt"]:
        research_only.append(f"open interest {(item.open_interest_usdt or 0) / 1e6:.1f}M USDT")
    if item.spread_bps is None or item.spread_bps > filters["max_spread_bps"]:
        research_only.append(f"spread {item.spread_bps} bps")
    if research_only:
        item.category = "RESEARCH_ONLY"
        item.reasons = research_only
    elif item.tier == "CORE":
        item.category = "CORE"
    elif (item.annualized_volatility or 0.0) > filters["high_volatility_annualized"]:
        item.category = "HIGH_VOLATILITY"
        item.reasons = [f"annualized volatility {item.annualized_volatility:.0%}"]
    else:
        item.category = "LIQUID"
    return item


def select_first_wave(items: list[Instrument], size: int) -> list[Instrument]:
    eligible = [item for item in items if item.category in {"CORE", "LIQUID", "HIGH_VOLATILITY"}]
    eligible.sort(key=lambda item: item.avg_daily_turnover_usdt or 0.0, reverse=True)
    return eligible[:size]


def annualized_volatility(closes: list[float]) -> float | None:
    returns = [math.log(b / a) for a, b in zip(closes, closes[1:]) if a > 0 and b > 0]
    if len(returns) < 10:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(365)


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def scan(config: dict[str, Any]) -> list[Instrument]:
    import ccxt

    exchange = getattr(ccxt, config["exchange"])(
        {"enableRateLimit": True, "options": {"defaultType": "swap"}}
    )
    markets = exchange.load_markets()
    tickers = exchange.fetch_tickers(params={"category": "linear"})
    now_ms = int(time.time() * 1000)
    items: list[Instrument] = []
    for tier, bases in config["candidates"].items():
        for base in bases:
            symbol = f"{base}/{config['quote']}:{config['settle']}"
            item = Instrument(base=base, tier=tier, symbol=symbol)
            market = markets.get(symbol)
            if market is None or not market.get("swap") or not market.get("linear"):
                items.append(classify(item, config["filters"]))
                continue
            info = market.get("info") or {}
            item.listed = True
            item.status = str(info.get("status", ""))
            launch = int(info.get("launchTime") or 0)
            if launch:
                item.launch_date = datetime.fromtimestamp(launch / 1000, UTC).date().isoformat()
                item.listing_age_days = (now_ms - launch) / DAY_MS
            item.delivery_time = str(info.get("deliveryTime", ""))
            item.contract_size = _float(market.get("contractSize"))
            item.tick_size = _float((info.get("priceFilter") or {}).get("tickSize"))
            lot = info.get("lotSizeFilter") or {}
            item.lot_step = _float(lot.get("qtyStep"))
            item.min_qty = _float(lot.get("minOrderQty"))
            item.min_notional = _float(lot.get("minNotionalValue"))
            item.max_leverage = _float((info.get("leverageFilter") or {}).get("maxLeverage"))
            interval = info.get("fundingInterval")
            item.funding_interval_min = int(interval) if interval else None

            ticker_info = (tickers.get(symbol) or {}).get("info") or {}
            item.turnover_24h_usdt = _float(ticker_info.get("turnover24h"))
            item.open_interest_usdt = _float(ticker_info.get("openInterestValue"))
            item.funding_rate = _float(ticker_info.get("fundingRate"))
            bid = _float(ticker_info.get("bid1Price"))
            ask = _float(ticker_info.get("ask1Price"))
            if bid and ask and ask >= bid:
                item.spread_bps = round((ask - bid) / ((ask + bid) / 2) * 10_000, 3)

            raw = exchange.publicGetV5MarketKline(
                {"category": "linear", "symbol": market["id"], "interval": "D", "limit": 31}
            )
            rows = sorted(raw["result"]["list"], key=lambda row: int(row[0]))
            closed = [row for row in rows if int(row[0]) + DAY_MS <= now_ms][-30:]
            if closed:
                item.avg_daily_turnover_usdt = sum(float(row[6]) for row in closed) / len(closed)
                item.annualized_volatility = annualized_volatility([float(row[4]) for row in closed])
            items.append(classify(item, config["filters"]))
    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan the futures asset universe.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    items = scan(config)
    wave = select_first_wave(items, config["first_wave_size"])
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "generated_at": stamp,
        "exchange": config["exchange"],
        "note": "Snapshot of current liquidity. Not a point-in-time universe.",
        "first_wave": [item.symbol for item in wave],
        "instruments": [asdict(item) for item in items],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    for item in items:
        turnover = (item.avg_daily_turnover_usdt or 0) / 1e6
        print(f"{item.symbol:<18} {item.category:<16} {turnover:>9.1f}M  {'; '.join(item.reasons)}")
    print("first wave:", ", ".join(payload["first_wave"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
