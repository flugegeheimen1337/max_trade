"""Validate Freqtrade candle files. Feather loading uses the engine image."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from market.data_quality import (
    TIMEFRAME_MS,
    Candle,
    DataQualityReport,
    epoch_millis,
    validate_candles,
)

FILENAME = {
    "BTC/USDT": "BTC_USDT",
    "ETH/USDT": "ETH_USDT",
}


def parse_candle_filename(path: Path) -> tuple[str, str] | None:
    stem = path.name
    for suffix in (".feather", ".json"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    else:
        return None
    if "-" not in stem:
        return None
    pair_token, timeframe = stem.rsplit("-", 1)
    if timeframe not in TIMEFRAME_MS:
        return None
    pair = pair_token.replace("_", "/", 1)
    return pair, timeframe


def candles_from_json(path: Path) -> list[Candle]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candles: list[Candle] = []
    for row in payload:
        candles.append((int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])))
    return candles


def candles_from_feather(path: Path) -> list[Candle]:
    import pandas as pd

    frame = pd.read_feather(path)
    if "date" not in frame.columns:
        raise ValueError(f"{path} has no date column.")
    dates = frame["date"]
    if getattr(dates.dt, "tz", None) is None:
        raise ValueError(f"{path} date column has no timezone. Expected UTC.")
    if str(dates.dt.tz) != "UTC":
        raise ValueError(f"{path} date timezone is {dates.dt.tz}, expected UTC.")
    timestamps = [epoch_millis(int(value)) for value in dates.astype("int64")]
    candles: list[Candle] = []
    for timestamp, opened, high, low, closed, volume in zip(
        timestamps,
        frame["open"],
        frame["high"],
        frame["low"],
        frame["close"],
        frame["volume"],
        strict=True,
    ):
        candles.append((int(timestamp), float(opened), float(high), float(low), float(closed), float(volume)))
    return candles


def load_candles(path: Path) -> list[Candle]:
    if path.suffix == ".json":
        return candles_from_json(path)
    if path.suffix == ".feather":
        return candles_from_feather(path)
    raise ValueError(f"Unsupported candle file {path.name}.")


def validate_directory(data_dir: Path) -> tuple[list[DataQualityReport], list[str]]:
    reports: list[DataQualityReport] = []
    notes: list[str] = []
    files = sorted(path for path in data_dir.rglob("*") if path.suffix in {".json", ".feather"})
    candle_files = [path for path in files if parse_candle_filename(path)]
    if not candle_files:
        notes.append(f"No candle files under {data_dir}.")
        return reports, notes
    for path in candle_files:
        parsed = parse_candle_filename(path)
        assert parsed is not None
        pair, timeframe = parsed
        try:
            candles = load_candles(path)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            report = DataQualityReport()
            report.errors.append(f"{path}: {exc}")
            reports.append(report)
            continue
        reports.append(validate_candles(candles, timeframe, f"{pair} {timeframe} ({path.name})"))
    return reports, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate downloaded OHLCV files.")
    parser.add_argument("--data-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    reports, notes = validate_directory(args.data_dir)
    for note in notes:
        print(note)
    if not reports:
        return 2
    failed = False
    for report in reports:
        for error in report.errors:
            failed = True
            print(f"error: {error}")
        for warning in report.warnings:
            print(f"warning: {warning}")
        if report.rows and report.first_ts is not None and report.last_ts is not None:
            print(f"rows={report.rows} first={report.first_ts} last={report.last_ts} missing={report.missing_candles}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
