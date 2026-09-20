"""Integration cache file helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..credentials import CredentialProfile, get_profile
from ..paths import profile_cache_dir


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scope_path(profile: CredentialProfile, scope: str) -> Path:
    return profile_cache_dir(profile.cache_key) / "integrations" / f"{scope}.json"


def write_scope_cache(
    profile: CredentialProfile | str,
    scope: str,
    payload: dict[str, Any],
) -> Path:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    path = _scope_path(resolved, scope)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "profile": resolved.slug,
        "scope": scope,
        "refreshed_at": _utc_now_iso(),
        **payload,
    }
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_scope_cache(profile: CredentialProfile | str, scope: str) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    path = _scope_path(resolved, scope)
    if not path.is_file():
        return {"profile": resolved.slug, "scope": scope, "refreshed_at": None}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {"profile": resolved.slug, "scope": scope}
