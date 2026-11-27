"""Compare two Freqtrade backtest exports after removing wall-clock fields."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

VOLATILE_KEYS = frozenset({"run_id", "backtest_start_time", "backtest_end_time"})


def load_backtest_report(path: Path) -> dict[str, Any]:
    if path.suffix != ".zip":
        raise ValueError(f"Expected a backtest zip, got {path.name}.")
    with zipfile.ZipFile(path) as archive:
        names = [
            name
            for name in archive.namelist()
            if name.endswith(".json") and not name.endswith("_config.json")
        ]
        if len(names) != 1:
            raise ValueError(f"{path.name} does not contain one backtest report.")
        return json.loads(archive.read(names[0]))


def canonical_report(payload: dict[str, Any]) -> dict[str, Any]:
    return _strip(payload)


def reports_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return canonical_report(left) == canonical_report(right)


def trade_count(payload: dict[str, Any]) -> int | None:
    strategy = payload.get("strategy")
    if not isinstance(strategy, dict) or len(strategy) != 1:
        return None
    result = next(iter(strategy.values()))
    trades = result.get("trades")
    if isinstance(trades, list):
        return len(trades)
    total = result.get("total_trades")
    if isinstance(total, int):
        return total
    return None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip(item)
            for key, item in value.items()
            if key not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_strip(item) for item in value]
    return value
