"""E02/E03 Bollinger and Z-Score Reversion, long and short.

Hypothesis: in a range (ADX below 20) a close more than two standard deviations
from the 20-bar mean returns to the mean. RSI must confirm the stretch; a low RSI
alone does not open a trade. Exit at the mean, by the stop, or after 48 bars.
"""

from pandas import DataFrame
import talib.abstract as ta

from research.strategy_base import LabFuturesStrategy, mark_entry


class FtBollingerReversion(LabFuturesStrategy):
    max_hold_bars = 48

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["mid"] = dataframe["close"].rolling(20).mean()
        dataframe["std"] = dataframe["close"].rolling(20).std()
        dataframe["zscore"] = (dataframe["close"] - dataframe["mid"]) / dataframe["std"]
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        ranging = dataframe["adx"] < 20
        long = ranging & (dataframe["zscore"] < -2) & (dataframe["rsi"] < 35)
        short = ranging & (dataframe["zscore"] > 2) & (dataframe["rsi"] > 65)
        mark_entry(dataframe, long, "enter_long", "E02L")
        mark_entry(dataframe, short, "enter_short", "E02S")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["close"] >= dataframe["mid"], "exit_long"] = 1
        dataframe.loc[dataframe["close"] <= dataframe["mid"], "exit_short"] = 1
        return dataframe
