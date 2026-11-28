"""Create the local .env and the active Freqtrade config."""

from __future__ import annotations

import secrets
from pathlib import Path

from core.config_builder import LabSettings, load_base_config, render_config, write_config
from core.constants import PLACEHOLDER_SECRETS
from core.envfile import load_env_file, write_private

ENV_REPLACEMENTS = (
    ("API_PASSWORD", "change-me-local-only-password"),
    ("JWT_SECRET_KEY", "change-me-local-only-jwt-secret-key-32"),
    ("WS_TOKEN", "change-me-local-only-ws-token-32chars"),
)


def prepare_env(env_path: Path, example_path: Path) -> str:
    if env_path.exists():
        return "kept"
    text = example_path.read_text(encoding="utf-8")
    for _name, placeholder in ENV_REPLACEMENTS:
        text = text.replace(placeholder, secrets.token_urlsafe(32), 1)
    write_private(env_path, text)
    return "created"


def render_active_config(root: Path) -> tuple[LabSettings, Path]:
    settings = LabSettings.from_env_file(root / ".env")
    config = render_config(load_base_config(root / "configs" / "config.dryrun.json"), settings)
    destination = root / "user_data" / "config.active.json"
    write_config(destination, config)
    return settings, destination


def secrets_are_local(settings: LabSettings) -> bool:
    return (
        settings.api_password not in PLACEHOLDER_SECRETS
        and settings.jwt_secret_key not in PLACEHOLDER_SECRETS
        and settings.ws_token not in PLACEHOLDER_SECRETS
    )


def load_settings(root: Path) -> LabSettings:
    raw = load_env_file(root / ".env")
    return LabSettings.from_mapping(raw)
