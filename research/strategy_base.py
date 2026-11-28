"""Shared behaviour for futures research strategies. Backtest use only."""

from __future__ import annotations

from datetime import datetime

from pandas import DataFrame, Series

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


def mark_entry(dataframe: DataFrame, mask: Series, column: str, tag: str) -> None:
    if column not in dataframe.columns:
        dataframe[column] = 0
    if "enter_tag" not in dataframe.columns:
        dataframe["enter_tag"] = None
    dataframe.loc[mask, column] = 1
    dataframe.loc[mask, "enter_tag"] = tag


class LabFuturesStrategy(IStrategy):
    INTERFACE_VERSION = 3

    can_short: bool = True
    position_adjustment_enable = False

    timeframe = "15m"
    startup_candle_count: int = 220
    process_only_new_candles = True

    # Exits come from the signal, the stop, or max_hold_bars. ROI is disabled.
    minimal_roi = {"0": 100}
    # Replaced by the rendered config so one price distance holds at every leverage.
    stoploss = -0.04
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    max_hold_bars: int | None = None

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        return min(float(self.config.get("lab_leverage", 1.0)), max_leverage)

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> str | None:
        if self.max_hold_bars is None:
            return None
        from freqtrade.exchange import timeframe_to_minutes

        held = (current_time - trade.open_date_utc).total_seconds() / 60
        if held >= self.max_hold_bars * timeframe_to_minutes(self.timeframe):
            return "max_hold"
        return None
