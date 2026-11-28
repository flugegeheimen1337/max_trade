"""C01 Cross-sectional momentum, long and short.

Hypothesis: over a week, coins that outperformed the rest keep outperforming
and laggards keep lagging. Every pair is ranked by its 7-day return against
all whitelisted pairs at the same candle. Long the top 3 while the pair is
above EMA 50, short the bottom 3 while below it. Exit when the pair leaves the
top or bottom 6, or after one week.
"""

from __future__ import annotations

import pandas as pd
from pandas import DataFrame
import talib.abstract as ta

from research.strategy_base import LabFuturesStrategy, mark_entry

TOP = 3
KEEP = 6


class FtCrossMomentum(LabFuturesStrategy):
    timeframe = "4h"
    startup_candle_count = 60

    def _lookback(self) -> int:
        from freqtrade.exchange import timeframe_to_minutes

        return int(7 * 24 * 60 / timeframe_to_minutes(self.timeframe))

    @property
    def max_hold_bars(self) -> int:  # type: ignore[override]
        return self._lookback()

    def _ranks(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        if getattr(self, "_rank_cache", None) is None:
            lookback = self._lookback()
            returns = {}
            for pair in self.dp.current_whitelist():
                frame = self.dp.get_pair_dataframe(pair, self.timeframe)
                if frame is None or frame.empty:
                    continue
                returns[pair] = frame.set_index("date")["close"].pct_change(lookback)
            table = pd.DataFrame(returns)
            self._rank_cache = (
                table.rank(axis=1, ascending=False),
                table.rank(axis=1, ascending=True),
            )
        return self._rank_cache

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        best, worst = self._ranks()
        pair = metadata["pair"]
        dates = dataframe["date"]
        dataframe["rank_top"] = best[pair].reindex(dates).to_numpy() if pair in best else float("nan")
        dataframe["rank_bottom"] = worst[pair].reindex(dates).to_numpy() if pair in worst else float("nan")
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        long = (dataframe["rank_top"] <= TOP) & (dataframe["close"] > dataframe["ema50"])
        short = (dataframe["rank_bottom"] <= TOP) & (dataframe["close"] < dataframe["ema50"])
        mark_entry(dataframe, long, "enter_long", "C01L")
        mark_entry(dataframe, short, "enter_short", "C01S")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[~(dataframe["rank_top"] <= KEEP), "exit_long"] = 1
        dataframe.loc[~(dataframe["rank_bottom"] <= KEEP), "exit_short"] = 1
        return dataframe
