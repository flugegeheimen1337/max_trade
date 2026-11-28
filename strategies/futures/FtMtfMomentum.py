"""A06 Multi-Timeframe Momentum, long and short.

Hypothesis: 12-bar rate of change in the direction of the 4h EMA 50/200 trend,
with RSI in a momentum band and above-average volume, continues. The 4h values
come from closed 4h candles only. Exit when momentum turns.
"""

from pandas import DataFrame
import talib.abstract as ta
from freqtrade.strategy import informative

from research.strategy_base import LabFuturesStrategy, mark_entry


class FtMtfMomentum(LabFuturesStrategy):
    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["roc"] = ta.ROC(dataframe, timeperiod=12)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["volume_sma"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        volume_ok = dataframe["volume"] > dataframe["volume_sma"]
        up = dataframe["ema50_4h"] > dataframe["ema200_4h"]
        down = dataframe["ema50_4h"] < dataframe["ema200_4h"]
        long = (
            up
            & (dataframe["roc"] > 0)
            & dataframe["rsi"].between(50, 70, inclusive="neither")
            & (dataframe["close"] > dataframe["ema50"])
            & volume_ok
        )
        short = (
            down
            & (dataframe["roc"] < 0)
            & dataframe["rsi"].between(30, 50, inclusive="neither")
            & (dataframe["close"] < dataframe["ema50"])
            & volume_ok
        )
        mark_entry(dataframe, long, "enter_long", "A06L")
        mark_entry(dataframe, short, "enter_short", "A06S")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["roc"] < 0) | (dataframe["rsi"] < 45), "exit_long"] = 1
        dataframe.loc[(dataframe["roc"] > 0) | (dataframe["rsi"] > 55), "exit_short"] = 1
        return dataframe
