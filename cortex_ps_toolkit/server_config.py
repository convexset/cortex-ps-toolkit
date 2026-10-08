"""Server configuration loaded from JSON or YAML (data/server.config.*)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, MutableMapping

import yaml

from .paths import data_dir

DEFAULT_SERVER_CONFIG: dict[str, Any] = {
    "server_log_level": "DEBUG",
    "server_log_debug_truncation_threshold": 512,
    "threshold_ttl_in_min": 10,
    "copy_binding_cache_pause_seconds": 5,
    "copy_binding_resolve_retries": 3,
}

VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARN", "ERROR"})
_config_cache: dict[str, Any] | None = None


def server_config_search_paths() -> list[Path]:
    explicit = os.environ.get("CORTEX_PS_SERVER_CONFIG")
    if explicit:
        return [Path(explicit).expanduser().resolve()]
    root = data_dir()
    return [
        root / "server.config.yaml",
        root / "server.config.yml",
        root / "server.config.json",
    ]


def resolve_server_config_path() -> Path | None:
    for path in server_config_search_paths():
        if path.is_file():
            return path
    return None


def _load_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
    else:
        payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ValueError(f"Server config must be a mapping: {path}")
    return payload


def _normalize_config(raw: Mapping[str, Any]) -> dict[str, Any]:
    merged: MutableMapping[str, Any] = dict(DEFAULT_SERVER_CONFIG)
    for key in DEFAULT_SERVER_CONFIG:
        if key in raw:
            merged[key] = raw[key]

    level = str(merged.get("server_log_level") or "INFO").strip().upper()
    if level == "WARNING":
        level = "WARN"
    if level not in VALID_LOG_LEVELS:
        level = "INFO"
    merged["server_log_level"] = level

    try:
        threshold = int(merged.get("server_log_debug_truncation_threshold") or 512)
    except (TypeError, ValueError):
        threshold = 512
    merged["server_log_debug_truncation_threshold"] = max(32, threshold)

    try:
        ttl_min = int(merged.get("threshold_ttl_in_min") or 10)
    except (TypeError, ValueError):
        ttl_min = 10
    merged["threshold_ttl_in_min"] = max(1, ttl_min)

    return dict(merged)


def load_server_config(*, reload: bool = False) -> dict[str, Any]:
    """Load and cache server config; fall back to defaults when no file exists."""
    global _config_cache
    if _config_cache is not None and not reload:
        return dict(_config_cache)

    path = resolve_server_config_path()
    if path is None:
        _config_cache = dict(DEFAULT_SERVER_CONFIG)
        return dict(_config_cache)

    try:
        file_data = _load_file(path)
    except Exception as exc:
        raise RuntimeError(f"Failed to load server config from {path}: {exc}") from exc

    _config_cache = _normalize_config(file_data)
    return dict(_config_cache)


def server_log_level_name() -> str:
    env = os.environ.get("CORTEX_PS_LOG_LEVEL", "").strip().upper()
    if env:
        if env == "WARNING":
            env = "WARN"
        if env in VALID_LOG_LEVELS:
            return env
    return str(load_server_config().get("server_log_level") or "INFO")


def debug_truncation_threshold() -> int:
    env = os.environ.get("CORTEX_PS_LOG_TRUNCATION")
    if env:
        try:
            return max(32, int(env))
        except ValueError:
            pass
    return int(load_server_config().get("server_log_debug_truncation_threshold") or 512)


def threshold_ttl_seconds() -> int:
    env = os.environ.get("CORTEX_PS_THRESHOLD_TTL_MIN")
    if env:
        try:
            return max(30, int(env) * 60)
        except ValueError:
            pass
    minutes = int(load_server_config().get("threshold_ttl_in_min") or 10)
    return max(30, minutes * 60)


def copy_binding_cache_pause_seconds() -> float:
    env = os.environ.get("CORTEX_PS_COPY_BINDING_PAUSE_SEC")
    if env:
        try:
            return max(0.0, float(env))
        except ValueError:
            pass
    try:
        return max(0.0, float(load_server_config().get("copy_binding_cache_pause_seconds") or 5))
    except (TypeError, ValueError):
        return 5.0


def copy_binding_retry_pause_seconds(attempt: int) -> float:
    """Pause before binding retry refresh: 5s, 10s, 15s, … (attempt is 0-based)."""
    try:
        base = float(load_server_config().get("copy_binding_cache_pause_seconds") or 5)
    except (TypeError, ValueError):
        base = 5.0
    return max(0.0, base * (max(0, attempt) + 1))


def default_server_config_document() -> dict[str, Any]:
    """Default server config (logging, cache threshold, copy binding timing only)."""
    return dict(DEFAULT_SERVER_CONFIG)


def format_default_server_config_yaml() -> str:
    """Serialize default server config for ``data/server.config.yaml``."""
    header = (
        "# Cortex PS Toolkit server configuration.\n"
        "# Copy to data/server.config.yaml or set CORTEX_PS_SERVER_CONFIG to this path.\n"
        "# Generate: python -m cortex_ps_toolkit server-config write-default\n"
        "# Portable export field rules are code-only — see docs/PORTABLE_EXPORT_FIELDS.md\n"
        "\n"
    )
    body = yaml.safe_dump(
        default_server_config_document(),
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    return header + body


def write_default_server_config(
    path: Path | None = None,
    *,
    force: bool = False,
) -> Path:
    """Write default server config YAML (refuses to overwrite unless ``force``)."""
    target = path if path is not None else data_dir() / "server.config.yaml"
    target = target.expanduser().resolve()
    if target.is_file() and not force:
        raise FileExistsError(f"Server config already exists: {target} (use --force to replace)")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(format_default_server_config_yaml(), encoding="utf-8")
    return target


def copy_binding_resolve_retries() -> int:
    env = os.environ.get("CORTEX_PS_COPY_BINDING_RETRIES")
    if env:
        try:
            return max(0, int(env))
        except ValueError:
            pass
    try:
        return max(0, int(load_server_config().get("copy_binding_resolve_retries") or 3))
    except (TypeError, ValueError):
        return 3
