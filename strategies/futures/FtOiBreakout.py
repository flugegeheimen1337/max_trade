"""F01 Breakout confirmed by rising open interest, long and short.

Hypothesis: a 48-bar channel break that comes with open interest up more than
5% over 24 hours is new positioning and continues; breaks on falling OI are
short covering or liquidation and are skipped. Trend filter EMA 200. Exit at
the opposite 24-bar channel or after 72 bars.
"""

from pandas import DataFrame
import talib.abstract as ta

from research.market_data import open_interest
from research.strategy_base import LabFuturesStrategy, mark_entry


DEFAULTS = {"channel": 48, "oi_threshold": 0.05}


class FtOiBreakout(LabFuturesStrategy):
    timeframe = "1h"
    max_hold_bars = 72

    def _param(self, name: str) -> float:
        return float((self.config.get("lab_params") or {}).get(name, DEFAULTS[name]))

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        channel = int(self._param("channel"))
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["dc_upper"] = dataframe["high"].rolling(channel).max().shift(1)
        dataframe["dc_lower"] = dataframe["low"].rolling(channel).min().shift(1)
        dataframe["exit_upper"] = dataframe["high"].rolling(channel // 2).max().shift(1)
        dataframe["exit_lower"] = dataframe["low"].rolling(channel // 2).min().shift(1)
        oi = open_interest(dataframe, self.config["lab_oi_dir"], metadata["pair"])
        bars_per_day = int(24 * 60 / self._minutes())
        dataframe["oi_change"] = oi / oi.shift(bars_per_day) - 1
        return dataframe

    def _minutes(self) -> int:
        from freqtrade.exchange import timeframe_to_minutes

        return timeframe_to_minutes(self.timeframe)

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        threshold = self._param("oi_threshold")
        rising = dataframe["oi_change"] > threshold if threshold > 0 else dataframe["close"].notna()
        long = (dataframe["close"] > dataframe["dc_upper"]) & (dataframe["close"] > dataframe["ema200"]) & rising
        short = (dataframe["close"] < dataframe["dc_lower"]) & (dataframe["close"] < dataframe["ema200"]) & rising
        mark_entry(dataframe, long, "enter_long", "F01L")
        mark_entry(dataframe, short, "enter_short", "F01S")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["close"] < dataframe["exit_lower"], "exit_long"] = 1
        dataframe.loc[dataframe["close"] > dataframe["exit_upper"], "exit_short"] = 1
        return dataframe
