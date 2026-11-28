"""B05 Bollinger Squeeze with B07 volume confirmation, long and short.

Hypothesis: after the band width sits in its lowest fifth of the last 100 bars,
a close outside the band on 1.5x average volume, in the direction of EMA 200,
continues. The squeeze is measured on the previous closed bar. Exit when the
close returns to the middle band.
"""

from pandas import DataFrame
import talib.abstract as ta

from research.strategy_base import LabFuturesStrategy, mark_entry


class FtSqueezeBreakout(LabFuturesStrategy):
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        mid = dataframe["close"].rolling(20).mean()
        std = dataframe["close"].rolling(20).std()
        dataframe["bb_mid"] = mid
        dataframe["bb_upper"] = mid + 2 * std
        dataframe["bb_lower"] = mid - 2 * std
        width = (dataframe["bb_upper"] - dataframe["bb_lower"]) / mid
        threshold = width.rolling(100).quantile(0.2)
        dataframe["squeeze"] = (width.shift(1) <= threshold.shift(1)).astype(int)
        dataframe["rel_volume"] = dataframe["volume"] / dataframe["volume"].rolling(20).mean().shift(1)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        base = (dataframe["squeeze"] == 1) & (dataframe["rel_volume"] > 1.5)
        long = base & (dataframe["close"] > dataframe["bb_upper"]) & (dataframe["close"] > dataframe["ema200"])
        short = base & (dataframe["close"] < dataframe["bb_lower"]) & (dataframe["close"] < dataframe["ema200"])
        mark_entry(dataframe, long, "enter_long", "B05L")
        mark_entry(dataframe, short, "enter_short", "B05S")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["close"] < dataframe["bb_mid"], "exit_long"] = 1
        dataframe.loc[dataframe["close"] > dataframe["bb_mid"], "exit_short"] = 1
        return dataframe
