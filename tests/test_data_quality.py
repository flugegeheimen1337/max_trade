import json
from pathlib import Path

from market.data_quality import epoch_millis, validate_candles
from market.validate_data import candles_from_json, parse_candle_filename

STEP = 15 * 60 * 1000
START = STEP * 2_000_000


def _candle(timestamp: int, price: float = 100.0) -> tuple[int, float, float, float, float, float]:
    return (timestamp, price, price + 1, price - 1, price, 10.0)


def test_epoch_millis_accepts_freqtrade_clock_units():
    # 2021-07-05 00:00:00 UTC, a 4h boundary. Feather files may store any of these units.
    milliseconds = 1_625_443_200_000
    assert epoch_millis(milliseconds) == milliseconds
    assert epoch_millis(milliseconds * 1_000) == milliseconds
    assert epoch_millis(milliseconds * 1_000_000) == milliseconds
    assert epoch_millis(milliseconds // 1_000) == milliseconds
    report = validate_candles(
        [_candle(milliseconds), _candle(milliseconds + 4 * 60 * 60 * 1000)],
        "4h",
        "ETH/USDT",
    )
    assert report.ok
    assert report.errors == []


def test_aligned_series_has_no_findings():
    candles = [_candle(START + offset * STEP) for offset in range(4)]
    report = validate_candles(candles, "15m", "BTC/USDT")
    assert report.ok
    assert report.warnings == []
    assert report.missing_candles == 0


def test_gap_is_a_warning_and_is_not_filled():
    candles = [_candle(START), _candle(START + 3 * STEP)]
    report = validate_candles(candles, "15m", "BTC/USDT")
    assert report.ok
    assert report.missing_candles == 2
    assert report.rows == 2


def test_duplicate_misaligned_and_bad_ohlc_are_errors():
    duplicate = validate_candles([_candle(START), _candle(START)], "15m", "dup")
    assert any("duplicate" in error for error in duplicate.errors)

    misaligned = validate_candles([_candle(START + 1)], "15m", "grid")
    assert any("aligned" in error for error in misaligned.errors)

    broken = _candle(START)
    broken = (broken[0], broken[1], broken[1] - 5, broken[3], broken[4], broken[5])
    invalid = validate_candles([broken], "15m", "ohlc")
    assert any("OHLC" in error for error in invalid.errors)


def test_json_loader_and_filename(tmp_path: Path):
    assert parse_candle_filename(Path("BTC_USDT-15m.json")) == ("BTC/USDT", "15m")
    destination = tmp_path / "ETH_USDT-1h.json"
    destination.write_text(json.dumps([[START, 1, 2, 0.5, 1.5, 3]]), encoding="utf-8")
    assert parse_candle_filename(destination) == ("ETH/USDT", "1h")
    assert candles_from_json(destination) == [(START, 1.0, 2.0, 0.5, 1.5, 3.0)]
