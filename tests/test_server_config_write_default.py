"""Default server config generation."""

from __future__ import annotations

from pathlib import Path

import yaml

from cortex_ps_toolkit import server_config


def test_write_default_server_config(tmp_path: Path) -> None:
    target = tmp_path / "server.config.yaml"
    written = server_config.write_default_server_config(target, force=True)
    assert written == target
    payload = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert payload["server_log_level"] == "DEBUG"
    assert "portable_export" not in payload


def test_legacy_portable_export_in_yaml_ignored(tmp_path: Path, monkeypatch) -> None:
    server_config._config_cache = None
    path = tmp_path / "server.config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "server_log_level": "INFO",
                "portable_export": {"playbooks": {"exclude_top_level": ["noise"]}},
            },
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CORTEX_PS_SERVER_CONFIG", str(path))
    cfg = server_config.load_server_config(reload=True)
    assert "portable_export" not in cfg
    assert cfg["server_log_level"] == "INFO"
