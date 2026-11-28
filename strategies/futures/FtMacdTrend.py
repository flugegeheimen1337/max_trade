"""A08 MACD Trend Continuation, long and short.

Hypothesis: a MACD cross in the direction of EMA 200 while ADX shows a trend
continues. Exit on the opposite MACD cross.
"""

from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib

from research.strategy_base import LabFuturesStrategy, mark_entry


class FtMacdTrend(LabFuturesStrategy):
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"] = macd["macd"]
        dataframe["macd_signal"] = macd["macdsignal"]
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        trend = dataframe["adx"] > 20
        cross_up = qtpylib.crossed_above(dataframe["macd"], dataframe["macd_signal"])
        cross_down = qtpylib.crossed_below(dataframe["macd"], dataframe["macd_signal"])
        long = cross_up & (dataframe["macd"] > 0) & (dataframe["close"] > dataframe["ema200"]) & trend
        short = cross_down & (dataframe["macd"] < 0) & (dataframe["close"] < dataframe["ema200"]) & trend
        mark_entry(dataframe, long, "enter_long", "A08L")
        mark_entry(dataframe, short, "enter_short", "A08S")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[qtpylib.crossed_below(dataframe["macd"], dataframe["macd_signal"]), "exit_long"] = 1
        dataframe.loc[qtpylib.crossed_above(dataframe["macd"], dataframe["macd_signal"]), "exit_short"] = 1
        return dataframe
