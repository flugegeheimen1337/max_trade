import pytest

from scripts.labctl import candle_datadir


def test_backtest_reads_the_exchange_candle_directory():
    assert candle_datadir("bybit") == "/freqtrade/user_data/data/bybit"
    assert candle_datadir("OKX") == "/freqtrade/user_data/data/okx"


def test_candle_datadir_rejects_a_path():
    with pytest.raises(ValueError):
        candle_datadir("bybit/spot")
