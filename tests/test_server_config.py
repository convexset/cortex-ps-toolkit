"""Tests for server configuration loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from cortex_ps_toolkit import server_config


@pytest.fixture(autouse=True)
def _reset_config_cache(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CORTEX_PS_DATA_DIR", str(tmp_path))
    server_config._config_cache = None
    monkeypatch.delenv("CORTEX_PS_SERVER_CONFIG", raising=False)
    monkeypatch.delenv("CORTEX_PS_LOG_LEVEL", raising=False)
    monkeypatch.delenv("CORTEX_PS_THRESHOLD_TTL_MIN", raising=False)
    yield
    server_config._config_cache = None


def test_load_server_config_defaults_when_missing_file() -> None:
    cfg = server_config.load_server_config()
    assert cfg["server_log_level"] == "DEBUG"
    assert cfg["server_log_debug_truncation_threshold"] == 512
    assert cfg["threshold_ttl_in_min"] == 10


def test_load_server_config_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "server.config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "server_log_level": "INFO",
                "server_log_debug_truncation_threshold": 256,
                "threshold_ttl_in_min": 15,
            }
        ),
        encoding="utf-8",
    )
    cfg = server_config.load_server_config()
    assert cfg["server_log_level"] == "INFO"
    assert cfg["server_log_debug_truncation_threshold"] == 256
    assert cfg["threshold_ttl_in_min"] == 15


def test_load_server_config_from_json_via_env(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "custom.config.json"
    path.write_text(
        json.dumps({"server_log_level": "WARN", "threshold_ttl_in_min": 7}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CORTEX_PS_SERVER_CONFIG", str(path))
    server_config._config_cache = None
    cfg = server_config.load_server_config()
    assert cfg["server_log_level"] == "WARN"
    assert server_config.threshold_ttl_seconds() == 7 * 60


def test_invalid_log_level_falls_back_to_info(tmp_path: Path) -> None:
    path = tmp_path / "server.config.json"
    path.write_text(json.dumps({"server_log_level": "VERBOSE"}), encoding="utf-8")
    cfg = server_config.load_server_config()
    assert cfg["server_log_level"] == "INFO"
