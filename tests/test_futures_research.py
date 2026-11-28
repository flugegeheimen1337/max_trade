import json
import zipfile
from datetime import date
from pathlib import Path

import pytest

from core.preflight import evaluate
from research.futures_config import render_futures_config
from research.results import load_strategy_result, summarise
from research.universe import Instrument, classify, select_first_wave
from research.windows import split_windows

ROOT = Path(__file__).resolve().parents[1]
FILTERS = {
    "min_avg_daily_turnover_usdt": 20e6,
    "min_listing_age_days": 180,
    "min_open_interest_usdt": 20e6,
    "max_spread_bps": 5.0,
    "high_volatility_annualized": 1.0,
}


def instrument(**overrides):
    values = {
        "base": "SOL", "tier": "LIQUID", "symbol": "SOL/USDT:USDT", "listed": True,
        "status": "Trading", "listing_age_days": 900, "avg_daily_turnover_usdt": 500e6,
        "open_interest_usdt": 300e6, "spread_bps": 0.5, "annualized_volatility": 0.6,
    }
    values.update(overrides)
    return Instrument(**values)


def render(**overrides):
    base = json.loads((ROOT / "configs" / "config.futures-research.json").read_text())
    kwargs = {
        "exchange": "bybit", "pairs": ["BTC/USDT:USDT"], "timeframe": "15m", "leverage": 5.0,
        "notional_per_trade": 100.0, "price_stop": 0.04, "fee": 0.00055,
        "max_open_trades": 5, "wallet": 1000.0,
    }
    kwargs.update(overrides)
    return render_futures_config(base, **kwargs)


def test_classify_blocks_thin_and_unlisted_contracts():
    assert classify(instrument(listed=False), FILTERS).category == "BLOCKED"
    assert classify(instrument(avg_daily_turnover_usdt=5e6), FILTERS).category == "BLOCKED"
    assert classify(instrument(listing_age_days=30), FILTERS).category == "BLOCKED"
    assert classify(instrument(delivery_time="1767225600000"), FILTERS).category == "BLOCKED"


def test_classify_separates_research_only_and_volatile_contracts():
    assert classify(instrument(spread_bps=7.0), FILTERS).category == "RESEARCH_ONLY"
    assert classify(instrument(open_interest_usdt=1e6), FILTERS).category == "RESEARCH_ONLY"
    assert classify(instrument(annualized_volatility=1.4), FILTERS).category == "HIGH_VOLATILITY"
    assert classify(instrument(tier="CORE", annualized_volatility=1.4), FILTERS).category == "CORE"
    assert classify(instrument(), FILTERS).category == "LIQUID"


def test_first_wave_ranks_eligible_contracts_by_turnover():
    items = [
        classify(instrument(symbol="A", avg_daily_turnover_usdt=30e6), FILTERS),
        classify(instrument(symbol="B", avg_daily_turnover_usdt=90e6), FILTERS),
        classify(instrument(symbol="C", spread_bps=9.0), FILTERS),
    ]
    assert [item.symbol for item in select_first_wave(items, 5)] == ["B", "A"]


def test_rendered_config_keeps_notional_and_price_stop_across_leverage():
    config = render(leverage=5.0)
    assert config["dry_run"] is True
    assert config["margin_mode"] == "isolated"
    assert config["stake_amount"] == pytest.approx(20.0)
    assert config["stoploss"] == pytest.approx(-0.2)
    assert "api_server" not in config
    assert evaluate(config, "", "futures_research") == []


def test_rendered_config_rejects_unsafe_leverage():
    with pytest.raises(ValueError):
        render(leverage=20.0)
    with pytest.raises(ValueError):
        render(leverage=10.0, price_stop=0.12)


def test_futures_preflight_rejects_live_and_cross_margin():
    config = render()
    config["dry_run"] = False
    assert evaluate(config, "", "futures_research")
    config = render()
    config["margin_mode"] = "cross"
    assert evaluate(config, "", "futures_research")
    config = render()
    config["exchange"]["secret"] = "x"
    assert evaluate(config, "", "futures_research")


def test_split_windows_are_contiguous_and_ordered():
    windows = split_windows(date(2023, 1, 1), date(2025, 1, 1), {
        "development": 0.6, "validation": 0.2, "holdout": 0.2,
    })
    dev, val, hold = (windows[key].split("-") for key in ("development", "validation", "holdout"))
    assert dev[0] == "20230101" and hold[1] == "20250101"
    assert dev[1] == val[0] and val[1] == hold[0]


def test_engulfing_counts_an_open_equal_to_the_previous_close():
    import pandas as pd

    from research.event_study import patterns

    df = pd.DataFrame({
        "open": [10.0, 10.0, 9.0], "close": [10.0, 9.0, 10.5],
        "high": [10.2, 10.1, 10.6], "low": [9.8, 8.9, 8.9], "volume": [1.0, 1.0, 1.0],
    })
    mask, direction = patterns(df)["bull_engulfing"]
    assert direction == 1
    assert mask.tolist() == [False, False, True]


def test_pit_universe_uses_only_turnover_before_the_month():
    import pandas as pd

    from research.pit_universe import build

    days = pd.date_range("2024-01-01", "2024-02-29", freq="D", tz="UTC")
    early = pd.Series(100.0, index=days)
    late = pd.Series([1.0 if day < pd.Timestamp("2024-02-01", tz="UTC") else 1000.0 for day in days],
                     index=days)
    old = pd.Timestamp("2020-01-01", tz="UTC")
    months = [pd.Timestamp("2024-02-01", tz="UTC"), pd.Timestamp("2024-03-01", tz="UTC")]
    result = build({"A": early, "B": late}, {"A": old, "B": old}, months,
                   top=1, min_age_days=180, min_turnover=0.0)
    assert result == {"2024-02": ["A"], "2024-03": ["B"]}


def test_pit_universe_skips_young_contracts():
    import pandas as pd

    from research.pit_universe import build

    days = pd.date_range("2024-01-01", "2024-01-31", freq="D", tz="UTC")
    young = pd.Timestamp("2023-12-01", tz="UTC")
    result = build({"A": pd.Series(1e9, index=days)}, {"A": young},
                   [pd.Timestamp("2024-02-01", tz="UTC")], top=5, min_age_days=180, min_turnover=0.0)
    assert result == {"2024-02": []}


def test_open_interest_is_used_one_hour_after_its_timestamp(tmp_path):
    import pandas as pd

    from research.market_data import open_interest

    start = pd.Timestamp("2024-01-01", tz="UTC")
    (tmp_path / "BTC-1h.csv").write_text(
        "timestamp,open_interest_contracts\n"
        f"{int(start.timestamp() * 1000)},10\n"
        f"{int((start + pd.Timedelta(hours=1)).timestamp() * 1000)},20\n"
    )
    candles = pd.DataFrame({"date": pd.date_range(start, periods=3, freq="h", tz="UTC")})
    values = open_interest(candles, tmp_path, "BTC/USDT:USDT").tolist()
    assert pd.isna(values[0])
    assert values[1:] == [10, 20]


def test_parameter_grid_is_a_full_product_with_stable_labels():
    from scripts.futures import params_label, parse_grid

    grid = parse_grid(["channel=24,48", "oi_threshold=0,0.03"])
    assert len(grid) == 4
    assert {"channel": 48.0, "oi_threshold": 0.03} in grid
    assert params_label({"oi_threshold": 0.03, "channel": 48.0}) == "-channel48-oi_threshold0.03"
    assert parse_grid([]) == [{}]


def test_summarise_splits_long_short_and_counts_costs(tmp_path):
    trades = [
        {"pair": "BTC/USDT:USDT", "is_short": False, "profit_abs": 10.0, "amount": 1.0,
         "open_rate": 100.0, "close_rate": 110.0, "fee_open": 0.001, "fee_close": 0.001,
         "funding_fees": -0.5, "exit_reason": "exit_signal", "enter_tag": "L",
         "close_date": "2024-01-05 00:00:00+00:00"},
        {"pair": "ETH/USDT:USDT", "is_short": True, "profit_abs": -4.0, "amount": 1.0,
         "open_rate": 100.0, "close_rate": 104.0, "fee_open": 0.001, "fee_close": 0.001,
         "funding_fees": 0.2, "exit_reason": "liquidation", "enter_tag": "S",
         "close_date": "2024-02-05 00:00:00+00:00"},
    ]
    archive = tmp_path / "backtest-result-1.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("backtest-result-1.json", json.dumps({"strategy": {"X": {"trades": trades}}}))
        handle.writestr("backtest-result-1_config.json", "{}")
    name, result = load_strategy_result(archive)
    summary = summarise(result, 1000.0)
    assert name == "X"
    assert summary["trades"] == 2
    assert summary["net_profit_abs"] == pytest.approx(6.0)
    assert summary["profit_factor"] == pytest.approx(2.5)
    assert summary["long"]["trades"] == 1 and summary["short"]["trades"] == 1
    assert summary["fees_abs"] == pytest.approx(0.414)
    assert summary["funding_abs"] == pytest.approx(-0.3)
    assert summary["liquidations"] == 1
    assert summary["worst_month"] == pytest.approx(-0.004)
