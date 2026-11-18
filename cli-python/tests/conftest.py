"""Keep CLI tests isolated from the current user's configuration and state."""
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_cli_config(tmp_path_factory, monkeypatch):
    from wiserec_cli import config

    root = tmp_path_factory.mktemp("user-config")
    example = Path(__file__).resolve().parents[1] / "config.example.json"
    (root / "config.json").write_bytes(example.read_bytes())
    monkeypatch.setattr(config, "_user_config_dir", lambda name: root)
