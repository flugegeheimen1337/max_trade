"""Check OHLCV rows that a backtest is about to trust.

Missing exchange candles are reported and left empty. This module does not
synthesize prices.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TIMEFRAME_MS = {
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}

Candle = tuple[int, float, float, float, float, float]


@dataclass
class DataQualityReport:
    rows: int = 0
    first_ts: int | None = None
    last_ts: int | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_candles: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_candles(candles: list[Candle], timeframe: str, source: str) -> DataQualityReport:
    report = DataQualityReport(rows=len(candles))
    step = TIMEFRAME_MS.get(timeframe)
    if step is None:
        report.errors.append(f"{source}: unsupported timeframe {timeframe}.")
        return report
    if not candles:
        report.errors.append(f"{source}: file has no candles.")
        return report

    previous: int | None = None
    seen: set[int] = set()
    gap_messages = 0
    for index, candle in enumerate(candles):
        timestamp, opened, high, low, closed, volume = candle
        if timestamp in seen:
            report.errors.append(f"{source}: duplicate candle at {timestamp}.")
        seen.add(timestamp)
        if previous is not None and timestamp <= previous:
            report.errors.append(f"{source}: candles are not strictly increasing at row {index}.")
        if timestamp % step != 0:
            report.errors.append(f"{source}: candle {timestamp} is not aligned to {timeframe}.")
        if previous is not None and timestamp > previous:
            missing = (timestamp - previous) // step - 1
            if missing > 0:
                report.missing_candles += missing
                if gap_messages < 5:
                    report.warnings.append(
                        f"{source}: {missing} missing candle(s) after {previous}."
                    )
                    gap_messages += 1
        previous = timestamp
        prices = (opened, high, low, closed)
        if not all(_positive_finite(price) for price in prices):
            report.errors.append(f"{source}: non-positive price at {timestamp}.")
            continue
        if high < max(opened, closed, low) or low > min(opened, closed, high):
            report.errors.append(f"{source}: OHLC values disagree at {timestamp}.")
        if volume < 0 or volume != volume:
            report.errors.append(f"{source}: volume is invalid at {timestamp}.")

    report.first_ts = candles[0][0]
    report.last_ts = candles[-1][0]
    if report.missing_candles and gap_messages == 5:
        report.warnings.append(
            f"{source}: {report.missing_candles} missing candles in total. Rows were not filled."
        )
    return report


def _positive_finite(value: float) -> bool:
    return value > 0 and value == value and value != float("inf")
