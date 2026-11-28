#!/usr/bin/env python3
"""Local operator for the stage-1 lab. Run this on the PC that has Docker."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtesting.reproducibility import (  # noqa: E402
    file_sha256,
    load_backtest_report,
    reports_match,
    trade_count,
)
from core.constants import (  # noqa: E402
    ALLOWED_PAIRS,
    DISCLAIMER,
    FEE,
    FREQTRADE_IMAGE,
    STRATEGY_NAME,
    TIMEFRAMES,
)
from core.envfile import load_env_file  # noqa: E402
from core.freqtrade_api import ApiError, post_command  # noqa: E402
from core.preflight import evaluate, load_config  # noqa: E402
from core.workspace import load_settings, prepare_env, render_active_config  # noqa: E402

STRATEGY_FILE = ROOT / "strategies" / "BaselineTrendStrategy.py"
DATA_DIR = ROOT / "user_data" / "data"
RESULT_DIR = ROOT / "user_data" / "backtest_results"
SIDECAR = ROOT / "user_data" / "reproducibility.json"


def candle_datadir(exchange: str) -> str:
    """Spot candles live in data/<exchange>/.

    Freqtrade appends the exchange only when --datadir is omitted. Passing the
    parent data directory makes the backtest look beside the files download wrote.
    """
    name = exchange.strip().lower()
    if not name or any(char in name for char in "/\\."):
        raise ValueError(f"Unexpected exchange name: {exchange}")
    return f"/freqtrade/user_data/data/{name}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="labctl")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in (
        "doctor",
        "init",
        "download",
        "validate",
        "backtest",
        "verify",
        "up",
        "down",
        "start",
        "pause",
        "stop",
    ):
        sub.add_parser(name)
    logs = sub.add_parser("logs")
    logs.add_argument("--follow", action="store_true")
    args = parser.parse_args(argv)
    commands = {
        "doctor": cmd_doctor,
        "init": cmd_init,
        "download": cmd_download,
        "validate": cmd_validate,
        "backtest": cmd_backtest,
        "verify": cmd_verify,
        "up": cmd_up,
        "down": cmd_down,
        "start": lambda: cmd_api("start"),
        "pause": lambda: cmd_api("pause"),
        "stop": lambda: cmd_api("stop"),
        "logs": lambda: cmd_logs(args.follow),
    }
    try:
        return commands[args.command]()
    except (ValueError, ApiError) as exc:
        print(exc, file=sys.stderr)
        return 1


def cmd_doctor() -> int:
    print(f"python {sys.version.split()[0]}")
    print(f"image {FREQTRADE_IMAGE}")
    docker_ok = _tool_ok("docker")
    if docker_ok:
        subprocess.call(["docker", "compose", "version"], cwd=ROOT)
    else:
        print("docker was not found on PATH.")
    env_path = ROOT / ".env"
    print(f".env {'present' if env_path.exists() else 'missing'}")
    try:
        _settings, config_path = render_active_config(ROOT)
        config = load_config(config_path)
        strategy_text = STRATEGY_FILE.read_text(encoding="utf-8")
        safety = evaluate(config, strategy_text, "safety")
        trade = evaluate(config, strategy_text, "trade")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"config render failed: {exc}")
        return 1
    print("safety preflight passed." if not safety else "safety preflight failed.")
    for problem in safety:
        print(f"- {problem}")
    print("trade preflight passed." if not trade else "trade preflight blocked.")
    for problem in trade:
        print(f"- {problem}")
    candle_files = list(DATA_DIR.rglob("*.feather")) + list(DATA_DIR.rglob("*.json"))
    print(f"candle files {len(candle_files)}")
    if SIDECAR.exists():
        print(SIDECAR.read_text(encoding="utf-8"))
    else:
        print("No reproducibility record yet. Run verify after download.")
    if safety or not docker_ok:
        return 2
    return 0


def cmd_init() -> int:
    for relative in ("user_data/data", "user_data/logs", "user_data/backtest_results"):
        (ROOT / relative).mkdir(parents=True, exist_ok=True)
    status = prepare_env(ROOT / ".env", ROOT / ".env.example")
    settings, _path = render_active_config(ROOT)
    print(f".env {status}.")
    print(f"exchange {settings.exchange}.")
    print("Active config written. Exchange keys were left empty.")
    print("Next: ./scripts/lab.sh doctor")
    return 0


def cmd_download() -> int:
    settings, config_path = render_active_config(ROOT)
    blocked = _require_safety(config_path)
    if blocked:
        return blocked
    if not _tool_ok("docker"):
        print("Docker is required to download candles.", file=sys.stderr)
        return 2
    command = [
        "download-data",
        "--config",
        "/freqtrade/user_data/config.active.json",
        "--exchange",
        settings.exchange,
        "--pairs",
        *ALLOWED_PAIRS,
        "--timeframes",
        *TIMEFRAMES,
        "--timerange",
        settings.download_timerange,
        "--trading-mode",
        "spot",
        "--data-format-ohlcv",
        "feather",
    ]
    code = _compose(command)
    if code != 0:
        return code
    return cmd_validate()


def cmd_validate() -> int:
    if not _tool_ok("docker"):
        print("Docker is required to read Freqtrade feather files.", file=sys.stderr)
        return 2
    return _compose(
        ["-m", "market.validate_data", "--data-dir", "/freqtrade/user_data/data"],
        entrypoint="python3",
    )


def cmd_backtest() -> int:
    settings, config_path = render_active_config(ROOT)
    blocked = _require_safety(config_path)
    if blocked:
        return blocked
    if not _tool_ok("docker"):
        print("Docker is required to run the backtest.", file=sys.stderr)
        return 2
    return _backtest(settings.verify_timerange, "backtest.log", settings.exchange)


def cmd_verify() -> int:
    settings, config_path = render_active_config(ROOT)
    blocked = _require_safety(config_path)
    if blocked:
        return blocked
    if not _tool_ok("docker"):
        print("Docker is required to verify the backtest.", file=sys.stderr)
        return 2
    before = _zip_set()
    first = _backtest(settings.verify_timerange, "backtest-1.log", settings.exchange)
    if first != 0:
        return first
    first_zip = _newest(_zip_set() - before)
    before = _zip_set()
    second = _backtest(settings.verify_timerange, "backtest-2.log", settings.exchange)
    if second != 0:
        return second
    second_zip = _newest(_zip_set() - before)
    if first_zip is None or second_zip is None:
        print("Freqtrade did not write two backtest archives.", file=sys.stderr)
        return 1
    left = load_backtest_report(first_zip)
    right = load_backtest_report(second_zip)
    matched = reports_match(left, right)
    count = trade_count(left)
    record = {
        "matched": matched,
        "trade_count": count,
        "timerange": settings.verify_timerange,
        "strategy": STRATEGY_NAME,
        "left_zip": first_zip.name,
        "right_zip": second_zip.name,
        "data_files": _data_hashes(),
        "disclaimer": DISCLAIMER,
    }
    SIDECAR.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))
    return 0 if matched else 1


def cmd_up() -> int:
    _settings, config_path = render_active_config(ROOT)
    blocked = _require_trade(config_path)
    if blocked:
        return blocked
    if not _tool_ok("docker"):
        print("Docker is required to start the container.", file=sys.stderr)
        return 2
    code = subprocess.call(["docker", "compose", "up", "-d"], cwd=ROOT, env=_docker_env())
    if code == 0:
        print("Dry-run container started in the stopped state. No virtual entries yet.")
        print("FreqUI: http://127.0.0.1:%s" % load_settings(ROOT).api_port)
        print("Username is in .env. Start the loop with ./scripts/lab.sh start")
    return code


def cmd_down() -> int:
    if not _tool_ok("docker"):
        print("Docker is required.", file=sys.stderr)
        return 2
    return subprocess.call(["docker", "compose", "down"], cwd=ROOT, env=_docker_env())


def cmd_api(command: str) -> int:
    settings = load_settings(ROOT)
    base = f"http://127.0.0.1:{settings.api_port}"
    body = post_command(base, settings.api_username, settings.api_password, command)
    print(body)
    return 0


def cmd_logs(follow: bool) -> int:
    if not _tool_ok("docker"):
        print("Docker is required.", file=sys.stderr)
        return 2
    command = ["docker", "compose", "logs", "--tail", "200"]
    if follow:
        command.append("--follow")
    return subprocess.call(command, cwd=ROOT, env=_docker_env())


def _require_safety(config_path: Path) -> int:
    problems = evaluate(load_config(config_path), STRATEGY_FILE.read_text(encoding="utf-8"), "safety")
    if not problems:
        return 0
    print("preflight failed:", file=sys.stderr)
    for problem in problems:
        print(f"- {problem}", file=sys.stderr)
    return 1


def _require_trade(config_path: Path) -> int:
    problems = evaluate(load_config(config_path), STRATEGY_FILE.read_text(encoding="utf-8"), "trade")
    if not problems:
        return 0
    print("preflight failed:", file=sys.stderr)
    for problem in problems:
        print(f"- {problem}", file=sys.stderr)
    return 1


def _backtest(timerange: str, logfile: str, exchange: str) -> int:
    return _compose(
        [
            "backtesting",
            "--config",
            "/freqtrade/user_data/config.active.json",
            "--strategy",
            STRATEGY_NAME,
            "--strategy-path",
            "/freqtrade/user_data/strategies",
            "--datadir",
            candle_datadir(exchange),
            "--timerange",
            timerange,
            "--fee",
            f"{FEE:.3f}",
            "--dry-run-wallet",
            "1000",
            "--cache",
            "none",
            "--export",
            "trades",
            "--backtest-directory",
            "/freqtrade/user_data/backtest_results",
            "--logfile",
            f"/freqtrade/user_data/logs/{logfile}",
        ]
    )


def _compose(args: list[str], entrypoint: str | None = None) -> int:
    command = ["docker", "compose", "run", "--rm", "-T", "--no-deps"]
    if entrypoint:
        command.extend(["--entrypoint", entrypoint])
    command.append("freqtrade")
    command.extend(args)
    return subprocess.call(command, cwd=ROOT, env=_docker_env())


def _docker_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(load_env_file(ROOT / ".env"))
    return env


def _tool_ok(name: str) -> bool:
    return shutil.which(name) is not None


def _zip_set() -> set[Path]:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    return set(RESULT_DIR.glob("backtest-result-*.zip"))


def _newest(paths: set[Path]) -> Path | None:
    if not paths:
        return None
    return max(paths, key=lambda path: path.stat().st_mtime)


def _data_hashes() -> list[dict[str, str]]:
    files = sorted(path for path in DATA_DIR.rglob("*") if path.suffix in {".feather", ".json"})
    return [{"name": str(path.relative_to(ROOT)), "sha256": file_sha256(path)} for path in files]


if __name__ == "__main__":
    raise SystemExit(main())
