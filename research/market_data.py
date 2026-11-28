"""Funding and open interest series aligned to candles without look-ahead."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def _merge_backward(dataframe: pd.DataFrame, series: pd.DataFrame, column: str) -> pd.Series:
    left = dataframe[["date"]].reset_index()
    series = series.assign(date=series["date"].astype(left["date"].dtype))
    merged = pd.merge_asof(left.sort_values("date"), series.sort_values("date"), on="date",
                           direction="backward")
    return merged.set_index("index")[column].reindex(dataframe.index)


def funding_rate(dataframe: pd.DataFrame, datadir: Path, pair: str) -> pd.Series:
    """Last funding rate settled at or before the candle open."""
    name = pair.replace("/", "_").replace(":", "_")
    path = Path(datadir) / "futures" / f"{name}-1h-funding_rate.feather"
    if not path.exists():
        return pd.Series(float("nan"), index=dataframe.index)
    funding = pd.read_feather(path)[["date", "funding_rate"]]
    return _merge_backward(dataframe, funding, "funding_rate")


def open_interest(dataframe: pd.DataFrame, oi_dir: Path, pair: str) -> pd.Series:
    """Hourly OI snapshot, usable one hour after its timestamp."""
    path = Path(oi_dir) / f"{pair.split('/')[0]}-1h.csv"
    if not path.exists():
        return pd.Series(float("nan"), index=dataframe.index)
    oi = pd.read_csv(path)
    oi["date"] = pd.to_datetime(oi["timestamp"], unit="ms", utc=True) + pd.Timedelta(hours=1)
    oi = oi.rename(columns={"open_interest_contracts": "oi"})[["date", "oi"]]
    return _merge_backward(dataframe, oi, "oi")
