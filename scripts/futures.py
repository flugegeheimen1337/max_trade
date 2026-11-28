#!/usr/bin/env python3
"""Host operator for futures research. Data downloads and backtests only."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.envfile import load_env_file  # noqa: E402
from research.futures_config import render_futures_config, write_json  # noqa: E402
from research.results import load_strategy_result, summarise  # noqa: E402
from research.windows import split_windows  # noqa: E402

RESEARCH_CONFIG = ROOT / "configs" / "futures_research.json"
BASE_CONFIG = ROOT / "configs" / "config.futures-research.json"
RESEARCH_DIR = ROOT / "user_data" / "research"
UNIVERSE_FILE = RESEARCH_DIR / "universe" / "latest.json"
RESULTS_FILE = RESEARCH_DIR / "results.jsonl"
PIT_FILE = RESEARCH_DIR / "universe" / "pit.json"
CONTAINER_ROOT = "/freqtrade/user_data"
STRATEGIES = (
    "FtEmaTrend",
    "FtDonchianTrend",
    "FtBollingerReversion",
    "FtSqueezeBreakout",
    "FtMacdTrend",
    "FtMtfMomentum",
    "FtFundingFade",
    "FtOiBreakout",
    "FtCrossMomentum",
)


def load_research() -> dict:
    return json.loads(RESEARCH_CONFIG.read_text(encoding="utf-8"))


def first_wave() -> list[str]:
    if not UNIVERSE_FILE.exists():
        raise SystemExit("Run ./scripts/futures.sh universe first.")
    return json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))["first_wave"]


def listed_candidates() -> list[str]:
    if not UNIVERSE_FILE.exists():
        raise SystemExit("Run ./scripts/futures.sh universe first.")
    payload = json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))
    return [item["symbol"] for item in payload["instruments"] if item["listed"]]


def pair_set(name: str) -> list[str]:
    return first_wave() if name == "first_wave" else listed_candidates()


def container_path(path: Path) -> str:
    return CONTAINER_ROOT + "/" + str(path.relative_to(ROOT / "user_data"))


def compose_run(args: list[str], config_path: Path, *, entrypoint: str | None = None) -> int:
    command = [
        "docker", "compose", "run", "--rm", "-T", "--no-deps",
        "-e", "LAB_MODE=futures_research",
        "-e", f"LAB_CONFIG={container_path(config_path)}",
    ]
    if entrypoint:
        command.extend(["--entrypoint", entrypoint])
    command.append("freqtrade")
    command.extend(args)
    env = os.environ.copy()
    env.update(load_env_file(ROOT / ".env"))
    return subprocess.call(command, cwd=ROOT, env=env)


def render(research: dict, pairs: list[str], timeframe: str, leverage: float, fee: float) -> dict:
    base = json.loads(BASE_CONFIG.read_text(encoding="utf-8"))
    return render_futures_config(
        base,
        exchange=research["exchange"],
        pairs=pairs,
        timeframe=timeframe,
        leverage=leverage,
        notional_per_trade=research["notional_per_trade_usdt"],
        price_stop=research["price_stop"],
        fee=fee,
        max_open_trades=research["max_open_trades"],
        wallet=research["wallet_usdt"],
    )


def cmd_universe() -> int:
    research = load_research()
    path = RESEARCH_DIR / "configs" / "universe.json"
    write_json(path, render(research, ["BTC/USDT:USDT"], "15m", 1.0, research["fees"]["taker"]))
    return compose_run(
        ["-m", "research.universe", "--config", "/lab/configs/futures_research.json",
         "--out", container_path(UNIVERSE_FILE)],
        path,
        entrypoint="python3",
    )


def cmd_download(timeframes: list[str], timerange: str | None, pairs: list[str]) -> int:
    research = load_research()
    path = RESEARCH_DIR / "configs" / "download.json"
    write_json(path, render(research, pairs, "15m", 1.0, research["fees"]["taker"]))
    return compose_run(
        [
            "download-data",
            "--config", container_path(path),
            "--exchange", research["exchange"],
            "--trading-mode", "futures",
            "--pairs", *pairs,
            "--timeframes", *timeframes,
            "--timerange", timerange or f"{research['history_start']}-",
            "--data-format-ohlcv", "feather",
            "--datadir", f"{CONTAINER_ROOT}/data/{research['exchange']}",
        ],
        path,
    )


def cmd_open_interest(pairs: list[str]) -> int:
    research = load_research()
    path = RESEARCH_DIR / "configs" / "open_interest.json"
    write_json(path, render(research, ["BTC/USDT:USDT"], "1h", 1.0, research["fees"]["taker"]))
    return compose_run(
        ["-m", "research.open_interest", "--pairs", *pairs,
         "--start", research["history_start"],
         "--out", container_path(RESEARCH_DIR / "market" / "open_interest")],
        path,
        entrypoint="python3",
    )


def cmd_pit_universe(top: int) -> int:
    research = load_research()
    path = RESEARCH_DIR / "configs" / "pit_universe.json"
    write_json(path, render(research, ["BTC/USDT:USDT"], "1h", 1.0, research["fees"]["taker"]))
    filters = research["filters"]
    return compose_run(
        ["-m", "research.pit_universe", "--datadir", f"{CONTAINER_ROOT}/data/{research['exchange']}",
         "--scan", container_path(UNIVERSE_FILE), "--start", research["history_start"],
         "--top", str(top), "--min-age-days", str(int(filters["min_listing_age_days"])),
         "--min-turnover", str(filters["min_avg_daily_turnover_usdt"]),
         "--out", container_path(PIT_FILE)],
        path,
        entrypoint="python3",
    )


def cmd_events(timeframes: list[str], window: str) -> int:
    research = load_research()
    if window == "holdout":
        raise SystemExit("The holdout window is reserved for the final test.")
    start, end = windows(research)[window].split("-")
    path = RESEARCH_DIR / "configs" / "events.json"
    write_json(path, render(research, ["BTC/USDT:USDT"], "1h", 1.0, research["fees"]["taker"]))
    return compose_run(
        ["-m", "research.event_study", "--datadir", f"{CONTAINER_ROOT}/data/{research['exchange']}",
         "--pairs", *first_wave(), "--timeframes", *timeframes, "--start", start, "--end", end,
         "--fee", str(research["fees"]["taker"]),
         "--out", container_path(RESEARCH_DIR / "events" / f"{window}.json")],
        path,
        entrypoint="python3",
    )


def windows(research: dict) -> dict[str, str]:
    start = datetime.strptime(research["history_start"], "%Y%m%d").date()
    end = datetime.now(UTC).date() - timedelta(days=1)
    return split_windows(start, end, research["split"])


def completed_runs() -> set[str]:
    if not RESULTS_FILE.exists():
        return set()
    done = set()
    for line in RESULTS_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            if record.get("status") == "DONE":
                done.add(record["run_id"])
    return done


def run_backtest(job: dict, research: dict) -> dict:
    run_id = job["run_id"]
    config_path = RESEARCH_DIR / "configs" / f"{run_id}.json"
    out_dir = RESEARCH_DIR / "backtests" / run_id
    log_dir = RESEARCH_DIR / "logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    config = render(research, job["pairs"], job["timeframe"], job["leverage"], job["fee"])
    config["lab_oi_dir"] = container_path(RESEARCH_DIR / "market" / "open_interest")
    if job.get("universe_file"):
        config["lab_universe_file"] = job["universe_file"]
    write_json(config_path, config)
    started = time.time()
    with (log_dir / f"{run_id}.stdout.log").open("w", encoding="utf-8") as handle:
        command = [
            "docker", "compose", "run", "--rm", "-T", "--no-deps",
            "-e", "LAB_MODE=futures_research",
            "-e", f"LAB_CONFIG={container_path(config_path)}",
            "freqtrade",
            "backtesting",
            "--config", container_path(config_path),
            "--strategy", job["strategy"],
            "--strategy-path", f"{CONTAINER_ROOT}/strategies/futures",
            "--datadir", f"{CONTAINER_ROOT}/data/{research['exchange']}",
            "--timerange", job["timerange"],
            "--cache", "none",
            "--export", "trades",
            "--backtest-directory", container_path(out_dir),
            "--logfile", container_path(log_dir / f"{run_id}.log"),
        ]
        env = os.environ.copy()
        env.update(load_env_file(ROOT / ".env"))
        code = subprocess.call(command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
    record = {key: value for key, value in job.items() if key != "pairs"}
    record.update({"pairs": len(job["pairs"]), "exit_code": code, "seconds": round(time.time() - started, 1)})
    zips = sorted(out_dir.glob("backtest-result-*.zip"))
    if code != 0 or not zips:
        record["status"] = "FAILED"
        return record
    _name, result = load_strategy_result(zips[-1])
    record["status"] = "DONE"
    record["validation_label"] = "LIMITED_VALIDATION"
    record["limitations"] = [
        "candidate list is today's (delisted coins are missing)" if job.get("universe_file")
        else "universe picked by today's liquidity (survivorship bias)",
        "no spread, slippage, latency or partial fills; stress fee stands in for them",
        "no intrabar detail: stops fill at the stop price",
    ]
    record["summary"] = summarise(result, research["wallet_usdt"])
    return record


def cmd_screen(strategies: list[str], timeframes: list[str], leverages: list[float],
               window: str, fee_label: str, workers: int, universe: str) -> int:
    research = load_research()
    pairs = pair_set("listed" if universe == "pit" else "first_wave")
    universe_file = container_path(PIT_FILE) if universe == "pit" else None
    if universe == "pit" and not PIT_FILE.exists():
        raise SystemExit("Run ./scripts/futures.sh pit-universe first.")
    timerange = windows(research)[window]
    if window == "holdout":
        raise SystemExit("The holdout window is reserved for the final test.")
    # "zero" is a diagnostic: it shows the gross edge before costs, never a tradable result.
    fee = 0.0 if fee_label == "zero" else research["fees"][fee_label]
    done = completed_runs()
    jobs = []
    for strategy in strategies:
        for timeframe in timeframes:
            for leverage in leverages:
                run_id = f"{window}-{strategy}-{timeframe}-x{leverage:g}-{fee_label}"
                if universe == "pit":
                    run_id = f"pit-{run_id}"
                if run_id in done:
                    continue
                jobs.append({
                    "run_id": run_id, "window": window, "timerange": timerange,
                    "strategy": strategy, "timeframe": timeframe, "leverage": leverage,
                    "fee_label": fee_label, "fee": fee, "pairs": pairs,
                    "universe": universe, "universe_file": universe_file,
                })
    print(f"{len(jobs)} runs queued, {workers} workers, window {window} {timerange}")
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_backtest, job, research): job for job in jobs}
        for future in as_completed(futures):
            record = future.result()
            with RESULTS_FILE.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
            summary = record.get("summary") or {}
            if record["status"] != "DONE":
                failures += 1
            print(
                f"{record['status']:<6} {record['run_id']:<55} trades={summary.get('trades')} "
                f"ret={summary.get('total_return')} pf={summary.get('profit_factor')} "
                f"dd={summary.get('max_drawdown_account')}",
                flush=True,
            )
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="futures")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("universe")
    sub.add_parser("windows")
    download = sub.add_parser("download")
    download.add_argument("--timeframes", nargs="+", default=["5m", "15m", "1h", "4h"])
    download.add_argument("--timerange")
    download.add_argument("--set", choices=("first_wave", "listed"), default="first_wave")
    oi = sub.add_parser("open-interest")
    oi.add_argument("--set", choices=("first_wave", "listed"), default="first_wave")
    pit = sub.add_parser("pit-universe")
    pit.add_argument("--top", type=int, default=12)
    events = sub.add_parser("events")
    events.add_argument("--timeframes", nargs="+", default=["15m", "1h"])
    events.add_argument("--window", choices=("development", "validation", "holdout"), default="development")
    screen = sub.add_parser("screen")
    screen.add_argument("--strategies", nargs="+", default=list(STRATEGIES))
    screen.add_argument("--timeframes", nargs="+", default=["15m", "1h"])
    screen.add_argument("--leverages", nargs="+", type=float, default=[1.0])
    screen.add_argument("--window", choices=("development", "validation", "holdout"), default="development")
    screen.add_argument("--fee", choices=("taker", "stress", "zero"), default="taker")
    screen.add_argument("--workers", type=int, default=4)
    screen.add_argument("--universe", choices=("first_wave", "pit"), default="first_wave")
    args = parser.parse_args(argv)
    if args.command == "universe":
        return cmd_universe()
    if args.command == "windows":
        print(json.dumps(windows(load_research()), indent=2))
        return 0
    if args.command == "download":
        return cmd_download(args.timeframes, args.timerange, pair_set(args.set))
    if args.command == "open-interest":
        return cmd_open_interest(pair_set(args.set))
    if args.command == "pit-universe":
        return cmd_pit_universe(args.top)
    if args.command == "events":
        return cmd_events(args.timeframes, args.window)
    if args.command == "screen":
        return cmd_screen(args.strategies, args.timeframes, args.leverages,
                          args.window, args.fee, args.workers, args.universe)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
