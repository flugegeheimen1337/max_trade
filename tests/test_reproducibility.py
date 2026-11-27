import json
import zipfile
from pathlib import Path

from backtesting.reproducibility import load_backtest_report, reports_match, trade_count
from core.constants import DISCLAIMER


def _report(profit: float, started: int) -> dict:
    return {
        "strategy": {
            "BaselineTrendStrategy": {
                "run_id": "changes-every-run",
                "backtest_start_time": started,
                "backtest_end_time": started + 10,
                "total_trades": 1,
                "profit_total_abs": profit,
                "trades": [{"pair": "BTC/USDT", "profit_abs": profit}],
            }
        }
    }


def test_wall_clock_fields_do_not_break_a_match():
    assert reports_match(_report(1.25, 100), _report(1.25, 999))
    assert trade_count(_report(1.25, 100)) == 1


def test_different_trade_results_do_not_match():
    assert not reports_match(_report(1.25, 100), _report(-4.0, 100))


def test_zip_report_loader(tmp_path: Path):
    archive = tmp_path / "backtest-result-2026-01-01_00-00-00.zip"
    report = _report(0.0, 1)
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("backtest-result-2026-01-01_00-00-00.json", json.dumps(report))
        handle.writestr("backtest-result-2026-01-01_00-00-00_config.json", "{}")
        handle.writestr("backtest-result-2026-01-01_00-00-00_BaselineTrendStrategy.py", "class X: pass")
    loaded = load_backtest_report(archive)
    assert reports_match(loaded, report)
    assert DISCLAIMER
