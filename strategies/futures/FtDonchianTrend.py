"""A09 Donchian Trend Following, long and short.

Hypothesis: a close beyond the 20-bar Donchian channel in the direction of EMA 200
continues. Channel bounds use only previous closed candles. The exit is a close
beyond the opposite 10-bar channel.
"""

from pandas import DataFrame
import talib.abstract as ta

from research.strategy_base import LabFuturesStrategy, mark_entry


class FtDonchianTrend(LabFuturesStrategy):
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["dc_upper"] = dataframe["high"].rolling(20).max().shift(1)
        dataframe["dc_lower"] = dataframe["low"].rolling(20).min().shift(1)
        dataframe["exit_upper"] = dataframe["high"].rolling(10).max().shift(1)
        dataframe["exit_lower"] = dataframe["low"].rolling(10).min().shift(1)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        long = (dataframe["close"] > dataframe["dc_upper"]) & (dataframe["close"] > dataframe["ema200"])
        short = (dataframe["close"] < dataframe["dc_lower"]) & (dataframe["close"] < dataframe["ema200"])
        mark_entry(dataframe, long, "enter_long", "A09L")
        mark_entry(dataframe, short, "enter_short", "A09S")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["close"] < dataframe["exit_lower"], "exit_long"] = 1
        dataframe.loc[dataframe["close"] > dataframe["exit_upper"], "exit_short"] = 1
        return dataframe
