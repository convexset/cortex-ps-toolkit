"""Toolkit settings persisted under data/collections/settings.json."""

from __future__ import annotations

import os
from typing import Any, Mapping, MutableMapping, Optional

from .collections import load_collection, save_collection
from .paths import collections_dir

DEFAULT_CACHE_TTL_SECONDS = 300
DEFAULT_MAX_INFLIGHT_PER_HOST = 5
DEFAULT_MAX_INFLIGHT_GLOBAL = 20
DEFAULT_REFACTOR_EXECUTION_MODE = "sequential"


def settings_path():
    return collections_dir() / "settings.json"


def default_settings() -> dict[str, Any]:
    return {
        "version": 1,
        "cache_ttl_seconds": DEFAULT_CACHE_TTL_SECONDS,
        "max_inflight_per_host": DEFAULT_MAX_INFLIGHT_PER_HOST,
        "max_inflight_global": DEFAULT_MAX_INFLIGHT_GLOBAL,
        "refactor_execution_mode": DEFAULT_REFACTOR_EXECUTION_MODE,
    }


def load_settings() -> dict[str, Any]:
    payload = load_collection(settings_path(), default=default_settings())
    payload.setdefault("version", 1)
    payload.setdefault("cache_ttl_seconds", DEFAULT_CACHE_TTL_SECONDS)
    payload.setdefault("max_inflight_per_host", DEFAULT_MAX_INFLIGHT_PER_HOST)
    payload.setdefault("max_inflight_global", DEFAULT_MAX_INFLIGHT_GLOBAL)
    payload.setdefault("refactor_execution_mode", DEFAULT_REFACTOR_EXECUTION_MODE)
    return payload


def save_settings(payload: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(default_settings())
    merged.update(payload)
    merged["version"] = 1
    ttl = int(merged.get("cache_ttl_seconds") or DEFAULT_CACHE_TTL_SECONDS)
    merged["cache_ttl_seconds"] = max(30, ttl)
    per_host = int(merged.get("max_inflight_per_host") or DEFAULT_MAX_INFLIGHT_PER_HOST)
    merged["max_inflight_per_host"] = max(1, per_host)
    global_max = int(merged.get("max_inflight_global") or DEFAULT_MAX_INFLIGHT_GLOBAL)
    merged["max_inflight_global"] = max(1, global_max)
    mode = str(merged.get("refactor_execution_mode") or DEFAULT_REFACTOR_EXECUTION_MODE).strip().lower()
    merged["refactor_execution_mode"] = mode if mode in ("sequential", "parallel") else DEFAULT_REFACTOR_EXECUTION_MODE
    save_collection(settings_path(), merged)
    return merged


def _int_from_env(name: str) -> Optional[int]:
    raw = os.environ.get(name)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def cache_ttl_seconds() -> int:
    env_raw = os.environ.get("CORTEX_PS_CACHE_TTL_SEC")
    if env_raw:
        try:
            return max(30, int(env_raw))
        except ValueError:
            pass
    settings = load_settings()
    try:
        return max(30, int(settings.get("cache_ttl_seconds") or DEFAULT_CACHE_TTL_SECONDS))
    except (TypeError, ValueError):
        return DEFAULT_CACHE_TTL_SECONDS


def max_inflight_per_host() -> int:
    env = _int_from_env("CORTEX_PS_MAX_INFLIGHT_PER_HOST")
    if env is not None:
        return max(1, env)
    settings = load_settings()
    try:
        return max(1, int(settings.get("max_inflight_per_host") or DEFAULT_MAX_INFLIGHT_PER_HOST))
    except (TypeError, ValueError):
        return DEFAULT_MAX_INFLIGHT_PER_HOST


def max_inflight_global() -> int:
    env = _int_from_env("CORTEX_PS_MAX_INFLIGHT_GLOBAL")
    if env is not None:
        return max(1, env)
    settings = load_settings()
    try:
        return max(1, int(settings.get("max_inflight_global") or DEFAULT_MAX_INFLIGHT_GLOBAL))
    except (TypeError, ValueError):
        return DEFAULT_MAX_INFLIGHT_GLOBAL


def default_max_inflight_per_host() -> int:
    return max_inflight_per_host()


def default_max_inflight_global() -> int:
    return max_inflight_global()


def profile_cache_ttl_seconds(profile) -> int:
    """Effective cache TTL for a credential profile (profile override, then global)."""
    from .credentials import CredentialProfile

    if isinstance(profile, CredentialProfile) and profile.cache_ttl_seconds is not None:
        return max(30, int(profile.cache_ttl_seconds))
    return cache_ttl_seconds()
