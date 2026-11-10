from __future__ import annotations

import os

from consensus import config


def test_env_file_override(tmp_path, monkeypatch):
    env_file = tmp_path / "custom.env"
    monkeypatch.setenv("CONSENSUS_ENV_FILE", str(env_file))

    assert config.get_env_file() == env_file


def test_environment_loads_without_overriding_real_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "CONSENSUS_TEST_VALUE=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONSENSUS_ENV_FILE", str(env_file))
    monkeypatch.setenv("CONSENSUS_TEST_VALUE", "from-environment")
    monkeypatch.setattr(config, "_LOADED", False)

    config.load_environment()

    assert os.getenv("CONSENSUS_TEST_VALUE") == "from-environment"
