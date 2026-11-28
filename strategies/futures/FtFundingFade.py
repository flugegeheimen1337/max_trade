"""G01 Funding extreme fade, long and short.

Hypothesis: when funding sits far above its 30-day norm, longs are crowded and
price tends to give back once momentum turns; the mirror holds for very
negative funding. Entry needs both the funding extreme and a close through
EMA 20 against the crowd. Exit at the opposite EMA 20 cross or after 24 bars.
"""

from pandas import DataFrame
import talib.abstract as ta

from research.market_data import funding_rate
from research.strategy_base import LabFuturesStrategy, mark_entry


class FtFundingFade(LabFuturesStrategy):
    timeframe = "1h"
    max_hold_bars = 24

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        rate = funding_rate(dataframe, self.config["datadir"], metadata["pair"])
        window = 30 * 24
        dataframe["funding"] = rate
        dataframe["funding_z"] = (rate - rate.rolling(window).mean()) / rate.rolling(window).std()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        crossed_down = (dataframe["close"] < dataframe["ema20"]) & (
            dataframe["close"].shift(1) >= dataframe["ema20"].shift(1))
        crossed_up = (dataframe["close"] > dataframe["ema20"]) & (
            dataframe["close"].shift(1) <= dataframe["ema20"].shift(1))
        short = (dataframe["funding_z"] > 2.0) & (dataframe["funding"] > 0) & crossed_down
        long = (dataframe["funding_z"] < -2.0) & (dataframe["funding"] < 0) & crossed_up
        mark_entry(dataframe, long, "enter_long", "G01L")
        mark_entry(dataframe, short, "enter_short", "G01S")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["close"] < dataframe["ema20"], "exit_long"] = 1
        dataframe.loc[dataframe["close"] > dataframe["ema20"], "exit_short"] = 1
        return dataframe
