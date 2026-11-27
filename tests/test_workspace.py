from pathlib import Path

from core.constants import FREQTRADE_IMAGE, PLACEHOLDER_SECRETS
from core.workspace import prepare_env

ROOT = Path(__file__).resolve().parents[1]


def test_init_replaces_placeholder_secrets(tmp_path: Path):
    destination = tmp_path / ".env"
    first = prepare_env(destination, ROOT / ".env.example")
    text = destination.read_text(encoding="utf-8")
    assert first == "created"
    for placeholder in PLACEHOLDER_SECRETS:
        if placeholder:
            assert placeholder not in text
    assert prepare_env(destination, ROOT / ".env.example") == "kept"


def test_compose_and_lock_pin_the_same_image():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    lock = (ROOT / "configs" / "versions.lock").read_text(encoding="utf-8")
    assert FREQTRADE_IMAGE in compose
    assert FREQTRADE_IMAGE in lock
    assert '127.0.0.1:${API_PORT:-8080}:8080' in compose
