from pathlib import Path

from core.config_builder import LabSettings, load_base_config, render_config
from core.preflight import evaluate

ROOT = Path(__file__).resolve().parents[1]
STRATEGY = (ROOT / "strategies" / "BaselineTrendStrategy.py").read_text(encoding="utf-8")


def _settings(**overrides: str) -> LabSettings:
    raw = {
        "EXCHANGE": "bybit",
        "API_USERNAME": "freqtrade",
        "API_PASSWORD": "local-password-local-password",
        "JWT_SECRET_KEY": "j" * 40,
        "WS_TOKEN": "w" * 40,
        "API_PORT": "8080",
        "DOWNLOAD_TIMERANGE": "20200101-",
        "VERIFY_TIMERANGE": "20240101-20240301",
    }
    raw.update(overrides)
    return LabSettings.from_mapping(raw)


def _config(**overrides: str) -> dict:
    config = render_config(load_base_config(ROOT / "configs" / "config.dryrun.json"), _settings())
    config.update(overrides)
    return config


def test_missing_exchange_defaults_to_bybit():
    assert LabSettings.from_mapping({}).exchange == "bybit"


def test_rendered_config_passes_trade_preflight():
    config = render_config(load_base_config(ROOT / "configs" / "config.dryrun.json"), _settings())
    assert config["exchange"]["name"] == "bybit"
    assert evaluate(config, STRATEGY, "trade") == []


def test_live_trading_flag_is_rejected_and_then_forced_off():
    base = load_base_config(ROOT / "configs" / "config.dryrun.json")
    base["dry_run"] = False
    base["exchange"]["api_key"] = "real-looking-key"
    base["exchange"]["secret"] = "real-looking-secret"
    rendered = render_config(base, _settings())
    assert rendered["dry_run"] is True
    assert rendered["exchange"]["api_key"] == ""
    assert rendered["exchange"]["secret"] == ""
    assert "key" not in rendered["exchange"]


def test_safety_blocks_a_hand_edited_live_config():
    config = _config()
    config["dry_run"] = False
    config["trading_mode"] = "futures"
    config["margin_mode"] = "isolated"
    config["exchange"]["api_key"] = "abc"
    config["exchange"]["pair_whitelist"] = ["DOGE/USDT"]
    config["api_server"]["listen_ip_address"] = "10.1.2.3"
    problems = evaluate(config, STRATEGY, "safety")
    assert any("dry_run" in problem for problem in problems)
    assert any("spot" in problem for problem in problems)
    assert any("api_key" in problem for problem in problems)
    assert any("whitelist" in problem for problem in problems)
    assert any("0.0.0.0" in problem for problem in problems)


def test_placeholder_secrets_block_trade_mode_only():
    config = render_config(
        load_base_config(ROOT / "configs" / "config.dryrun.json"),
        _settings(
            API_PASSWORD="change-me-local-only-password",
            JWT_SECRET_KEY="change-me-local-only-jwt-secret-key-32",
            WS_TOKEN="change-me-local-only-ws-token-32chars",
        ),
    )
    assert evaluate(config, STRATEGY, "safety") == []
    problems = evaluate(config, STRATEGY, "trade")
    assert len(problems) == 3


def test_short_strategy_text_is_rejected():
    problems = evaluate(_config(), "can_short: bool = True\n", "safety")
    assert any("can_short" in problem for problem in problems)
