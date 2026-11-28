"""Forward returns after simple candle and volume patterns.

Reads Freqtrade feather candles. A pattern is measured on the closed bar and
entered at the next bar open, so no future data leaks into the signal. Returns
are reported gross and after one round-trip taker fee, per direction.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

HORIZONS = (1, 4, 12, 24)


def patterns(df: pd.DataFrame) -> dict[str, tuple[pd.Series, int]]:
    body = df["close"] - df["open"]
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    upper = df["high"] - df[["open", "close"]].max(axis=1)
    lower = df[["open", "close"]].min(axis=1) - df["low"]
    prev_body = body.shift(1)
    rel_volume = df["volume"] / df["volume"].rolling(50).mean()
    ema200 = df["close"].ewm(span=200, adjust=False).mean()
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    inside = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))
    return {
        "baseline_every_bar": (pd.Series(True, index=df.index), 1),
        "bull_engulfing": (
            (prev_body < 0) & (body > 0) & (df["close"] > df["open"].shift(1))
            & (df["open"] <= df["close"].shift(1)), 1),
        "bear_engulfing": (
            (prev_body > 0) & (body < 0) & (df["close"] < df["open"].shift(1))
            & (df["open"] >= df["close"].shift(1)), -1),
        "hammer": ((lower > 2 * body.abs()) & (upper < 0.25 * rng) & (df["close"] < ema200), 1),
        "shooting_star": ((upper > 2 * body.abs()) & (lower < 0.25 * rng) & (df["close"] > ema200), -1),
        "inside_break_up": (inside.shift(1, fill_value=False) & (df["close"] > df["high"].shift(1)), 1),
        "inside_break_down": (inside.shift(1, fill_value=False) & (df["close"] < df["low"].shift(1)), -1),
        "volume_spike_up": ((rel_volume > 3) & (body > 0), 1),
        "volume_spike_down": ((rel_volume > 3) & (body < 0), -1),
        "volume_spike_fade_up": ((rel_volume > 3) & (body > 0), -1),
        "volume_spike_fade_down": ((rel_volume > 3) & (body < 0), 1),
        "rsi_oversold": ((rsi < 25) & (rsi.shift(1) >= 25), 1),
        "rsi_overbought": ((rsi > 75) & (rsi.shift(1) <= 75), -1),
    }


def forward_returns(df: pd.DataFrame, horizon: int) -> pd.Series:
    entry = df["open"].shift(-1)
    exit_ = df["open"].shift(-1 - horizon)
    return exit_ / entry - 1


def study(df: pd.DataFrame, fee: float) -> list[dict]:
    rows = []
    forward = {h: forward_returns(df, h) for h in HORIZONS}
    for name, (mask, direction) in patterns(df).items():
        mask = mask.fillna(False).astype(bool)
        for horizon, values in forward.items():
            sample = (values[mask].dropna() * direction)
            if sample.empty:
                continue
            rows.append({
                "pattern": name, "direction": "long" if direction > 0 else "short",
                "horizon_bars": horizon, "events": int(sample.size),
                "mean_gross": float(sample.mean()),
                "mean_net": float(sample.mean() - 2 * fee),
                "median_gross": float(sample.median()),
                "hit_rate": float((sample > 0).mean()),
                "t_stat": float(sample.mean() / (sample.std(ddof=1) / math.sqrt(sample.size)))
                if sample.size > 2 and sample.std(ddof=1) > 0 else None,
            })
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pattern event study on futures candles.")
    parser.add_argument("--datadir", type=Path, required=True)
    parser.add_argument("--pairs", nargs="+", required=True)
    parser.add_argument("--timeframes", nargs="+", required=True)
    parser.add_argument("--start", required=True, help="YYYYMMDD inclusive")
    parser.add_argument("--end", required=True, help="YYYYMMDD exclusive")
    parser.add_argument("--fee", type=float, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")
    records = []
    for timeframe in args.timeframes:
        for pair in args.pairs:
            path = args.datadir / "futures" / f"{pair.replace('/', '_').replace(':', '_')}-{timeframe}-futures.feather"
            if not path.exists():
                records.append({"pair": pair, "timeframe": timeframe, "status": "DATA_UNAVAILABLE"})
                continue
            df = pd.read_feather(path)
            df = df[(df["date"] >= start) & (df["date"] < end)].reset_index(drop=True)
            for row in study(df, args.fee):
                records.append({"pair": pair, "timeframe": timeframe, "status": "OK", **row})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([r for r in records if r["status"] == "OK"])
    pooled = []
    if not frame.empty:
        for keys, group in frame.groupby(["timeframe", "pattern", "direction", "horizon_bars"]):
            weights = group["events"]
            positive_pairs = int((group["mean_net"] > 0).sum())
            pooled.append({
                "timeframe": keys[0], "pattern": keys[1], "direction": keys[2], "horizon_bars": int(keys[3]),
                "events": int(weights.sum()),
                "mean_gross": float((group["mean_gross"] * weights).sum() / weights.sum()),
                "mean_net": float((group["mean_net"] * weights).sum() / weights.sum()),
                "hit_rate": float((group["hit_rate"] * weights).sum() / weights.sum()),
                "pairs_positive_net": positive_pairs, "pairs": int(len(group)),
            })
    payload = {"window": f"{args.start}-{args.end}", "fee": args.fee, "pooled": pooled, "per_pair": records}
    args.out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    baseline = {
        (r["timeframe"], r["horizon_bars"]): r["mean_gross"]
        for r in pooled if r["pattern"] == "baseline_every_bar"
    }
    for row in pooled:
        drift = baseline.get((row["timeframe"], row["horizon_bars"]), 0.0)
        sign = 1 if row["direction"] == "long" else -1
        row["excess_vs_drift"] = row["mean_gross"] - sign * drift
    payload["pooled"] = pooled
    args.out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    best = sorted(pooled, key=lambda r: r["mean_net"], reverse=True)[:10]
    for row in sorted(pooled, key=lambda r: r["excess_vs_drift"], reverse=True)[:10]:
        print(f"excess {row['timeframe']:>4} {row['pattern']:<24} {row['direction']:<5} h={row['horizon_bars']:>2} "
              f"n={row['events']:>6} excess={row['excess_vs_drift'] * 100:+.3f}% net={row['mean_net'] * 100:+.3f}%")
    for row in best:
        print(f"{row['timeframe']:>4} {row['pattern']:<24} {row['direction']:<5} h={row['horizon_bars']:>2} "
              f"n={row['events']:>6} net={row['mean_net'] * 100:+.3f}% hit={row['hit_rate']:.2f} "
              f"pairs+={row['pairs_positive_net']}/{row['pairs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
