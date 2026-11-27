"""Spot trend probe used to prove the engine repeats a backtest.

Hypothesis: a long is allowed after price holds above EMA 200, EMA 20 is above
EMA 50, ADX shows a trend, RSI is not stretched, and volume is above its
average. The exit is a loss of that trend or the fixed stop.

This is an engine check for stage 1. It is not a tuned strategy and it does
not use the 1h, 4h, or 1d candles that the downloader stores for later work.
"""

from pandas import DataFrame

from freqtrade.strategy import IStrategy
import talib.abstract as ta


class BaselineTrendStrategy(IStrategy):
    INTERFACE_VERSION = 3

    can_short: bool = False
    position_adjustment_enable = False

    timeframe = "15m"
    startup_candle_count: int = 220
    process_only_new_candles = True

    # Disable ROI so the probe exits on the signal or the stop.
    minimal_roi = {"0": 100}
    stoploss = -0.08
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    plot_config = {
        "main_plot": {
            "ema20": {"color": "yellow"},
            "ema50": {"color": "orange"},
            "ema200": {"color": "white"},
        },
        "subplots": {
            "ADX": {"adx": {"color": "blue"}},
            "RSI": {"rsi": {"color": "red"}},
        },
    }

    def informative_pairs(self):
        return []

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["volume_sma"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        conditions = (
            (dataframe["close"] > dataframe["ema200"])
            & (dataframe["ema20"] > dataframe["ema50"])
            & (dataframe["adx"] > 20)
            & (dataframe["rsi"] > 45)
            & (dataframe["rsi"] < 65)
            & (dataframe["volume"] > dataframe["volume_sma"])
        )
        dataframe.loc[conditions, "enter_long"] = 1
        dataframe.loc[conditions, "enter_tag"] = "baseline-trend"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe.loc[
            (dataframe["ema20"] < dataframe["ema50"]) | (dataframe["close"] < dataframe["ema200"]),
            "exit_long",
        ] = 1
        return dataframe
