"""Print screening results from results.jsonl as Markdown tables."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> list[dict]:
    latest: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            if record.get("status") == "DONE":
                latest[record["run_id"]] = record
    return list(latest.values())


def pct(value) -> str:
    return "-" if value is None else f"{value * 100:+.1f}%"


def num(value, digits: int = 2) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def table(records: list[dict]) -> str:
    lines = [
        "| run | trades | return | PF | max DD | fees | funding | liq | long PnL / PF | short PnL / PF |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in sorted(records, key=lambda r: r["summary"]["total_return"], reverse=True):
        s = r["summary"]
        lines.append(
            f"| {r['strategy']} {r['timeframe']} x{r['leverage']:g} {r['fee_label']} | {s['trades']} "
            f"| {pct(s['total_return'])} | {num(s['profit_factor'])} | {num((s['max_drawdown_account'] or 0) * 100, 1)}% "
            f"| {num(s['fees_abs'], 0)} | {num(s['funding_abs'], 0)} | {s['liquidations']} "
            f"| {num(s['long']['profit_abs'], 0)} / {num(s['long']['profit_factor'])} "
            f"| {num(s['short']['profit_abs'], 0)} / {num(s['short']['profit_factor'])} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--window")
    parser.add_argument("--fee")
    parser.add_argument("--by-pair", help="run_id to break down by pair")
    args = parser.parse_args(argv)
    records = load(args.results)
    if args.window:
        records = [r for r in records if r["window"] == args.window]
    if args.fee:
        records = [r for r in records if r["fee_label"] == args.fee]
    if args.by_pair:
        record = next(r for r in records if r["run_id"] == args.by_pair)
        print("| pair | trades | PnL | PF | win rate |\n|---|---:|---:|---:|---:|")
        for pair, side in sorted(record["summary"]["by_pair"].items(), key=lambda kv: kv[1]["profit_abs"]):
            print(f"| {pair} | {side['trades']} | {side['profit_abs']:.1f} | {num(side['profit_factor'])} "
                  f"| {num(side['win_rate'])} |")
        return 0
    print(table(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
