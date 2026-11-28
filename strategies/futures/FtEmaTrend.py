"""A01 EMA Trend Long and A02 EMA Trend Short.

Hypothesis: a position in the direction of EMA 200 and EMA 20/50 is allowed when
ADX shows a trend, RSI is not stretched, and volume is above its average. The
long rules are the stage-1 baseline. The short rules mirror them.
"""

from pandas import DataFrame
import talib.abstract as ta

from research.strategy_base import LabFuturesStrategy, mark_entry


class FtEmaTrend(LabFuturesStrategy):
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["volume_sma"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        volume_ok = dataframe["volume"] > dataframe["volume_sma"]
        trend = dataframe["adx"] > 20
        long = (
            (dataframe["close"] > dataframe["ema200"])
            & (dataframe["ema20"] > dataframe["ema50"])
            & trend
            & dataframe["rsi"].between(45, 65, inclusive="neither")
            & volume_ok
        )
        short = (
            (dataframe["close"] < dataframe["ema200"])
            & (dataframe["ema20"] < dataframe["ema50"])
            & trend
            & dataframe["rsi"].between(35, 55, inclusive="neither")
            & volume_ok
        )
        mark_entry(dataframe, long, "enter_long", "A01")
        mark_entry(dataframe, short, "enter_short", "A02")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["ema20"] < dataframe["ema50"]) | (dataframe["close"] < dataframe["ema200"]),
            "exit_long",
        ] = 1
        dataframe.loc[
            (dataframe["ema20"] > dataframe["ema50"]) | (dataframe["close"] > dataframe["ema200"]),
            "exit_short",
        ] = 1
        return dataframe
