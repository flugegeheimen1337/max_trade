"""Download hourly open-interest history from Bybit public endpoints (no keys)."""

from __future__ import annotations

import argparse
import csv
import time
from datetime import UTC, datetime
from pathlib import Path

HOUR_MS = 3_600_000
PAGE = 200


def fetch_pair(exchange, market_id: str, start_ms: int, end_ms: int) -> list[tuple[int, float]]:
    rows: dict[int, float] = {}
    cursor_end = end_ms
    while cursor_end > start_ms:
        page_start = max(start_ms, cursor_end - PAGE * HOUR_MS)
        raw = exchange.publicGetV5MarketOpenInterest({
            "category": "linear", "symbol": market_id, "intervalTime": "1h",
            "startTime": page_start, "endTime": cursor_end, "limit": PAGE,
        })
        items = raw["result"]["list"]
        for item in items:
            rows[int(item["timestamp"])] = float(item["openInterest"])
        cursor_end = page_start
        if not items and page_start == start_ms:
            break
    return sorted(rows.items())


def main(argv: list[str] | None = None) -> int:
    import ccxt

    parser = argparse.ArgumentParser(description="Download hourly open interest.")
    parser.add_argument("--pairs", nargs="+", required=True)
    parser.add_argument("--start", required=True, help="YYYYMMDD")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    exchange = ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    markets = exchange.load_markets()
    start_ms = int(datetime.strptime(args.start, "%Y%m%d").replace(tzinfo=UTC).timestamp() * 1000)
    end_ms = int(time.time() * 1000) // HOUR_MS * HOUR_MS
    args.out.mkdir(parents=True, exist_ok=True)
    for pair in args.pairs:
        rows = fetch_pair(exchange, markets[pair]["id"], start_ms, end_ms)
        path = args.out / f"{pair.split('/')[0]}-1h.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["timestamp", "open_interest_contracts"])
            writer.writerows(rows)
        first = datetime.fromtimestamp(rows[0][0] / 1000, UTC).isoformat() if rows else "-"
        print(f"{pair:<18} rows={len(rows):>6} first={first}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
