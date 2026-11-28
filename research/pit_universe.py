"""Point-in-time monthly universe built only from data known before each month.

A pair enters month M when, using candles strictly before M, its 30-day average
daily turnover ranks in the top N and its contract had been listed for the
minimum age. Turnover is approximated from candles as volume x close.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


def candle_file(datadir: Path, pair: str, timeframe: str) -> Path:
    name = pair.replace("/", "_").replace(":", "_")
    return datadir / "futures" / f"{name}-{timeframe}-futures.feather"


def daily_turnover(datadir: Path, pair: str) -> pd.Series | None:
    path = candle_file(datadir, pair, "1h")
    if not path.exists():
        return None
    df = pd.read_feather(path)
    turnover = (df["volume"] * df["close"]).groupby(df["date"].dt.floor("D")).sum()
    return turnover


def build(
    turnover: dict[str, pd.Series],
    launch: dict[str, pd.Timestamp | None],
    months: list[pd.Timestamp],
    *,
    top: int,
    min_age_days: int,
    min_turnover: float,
    lookback_days: int = 30,
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for month in months:
        window_start = month - pd.Timedelta(days=lookback_days)
        ranked = []
        for pair, series in turnover.items():
            listed = launch.get(pair)
            if listed is None or (month - listed).days < min_age_days:
                continue
            window = series[(series.index >= window_start) & (series.index < month)]
            if len(window) < lookback_days:
                continue
            average = float(window.mean())
            if average >= min_turnover:
                ranked.append((average, pair))
        ranked.sort(reverse=True)
        result[month.strftime("%Y-%m")] = [pair for _, pair in ranked[:top]]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a point-in-time monthly universe.")
    parser.add_argument("--datadir", type=Path, required=True)
    parser.add_argument("--scan", type=Path, required=True, help="universe scan with launch dates")
    parser.add_argument("--start", required=True, help="YYYYMMDD")
    parser.add_argument("--top", type=int, required=True)
    parser.add_argument("--min-age-days", type=int, required=True)
    parser.add_argument("--min-turnover", type=float, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    scan = json.loads(args.scan.read_text(encoding="utf-8"))
    launch: dict[str, pd.Timestamp | None] = {}
    turnover: dict[str, pd.Series] = {}
    for item in scan["instruments"]:
        if not item["listed"]:
            continue
        pair = item["symbol"]
        launch[pair] = pd.Timestamp(item["launch_date"], tz="UTC") if item["launch_date"] else None
        series = daily_turnover(args.datadir, pair)
        if series is not None:
            turnover[pair] = series
    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(datetime.now(UTC).date(), tz="UTC")
    months = list(pd.date_range(start, end, freq="MS", tz="UTC"))
    result = build(turnover, launch, months, top=args.top,
                   min_age_days=args.min_age_days, min_turnover=args.min_turnover)
    payload = {
        "rule": f"top {args.top} by 30d turnover before the month, listed >= {args.min_age_days} days, "
                f"turnover >= {args.min_turnover:,.0f} USDT/day",
        "caveat": "Candidates are today's listed contracts; contracts delisted before today are missing.",
        "months": result,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    for month, pairs in result.items():
        print(month, len(pairs), " ".join(p.split("/")[0] for p in pairs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
