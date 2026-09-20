"""On-disk script cache under data/cache/{cache_key}/scripts/."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from ..credentials import CredentialProfile
from ..paths import cache_root


def scripts_cache_dir(profile: CredentialProfile) -> Path:
    return cache_root() / profile.cache_key / "scripts"


def scripts_index_path(profile: CredentialProfile) -> Path:
    return scripts_cache_dir(profile) / "index.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_scripts_index(profile: CredentialProfile) -> dict[str, Any]:
    path = scripts_index_path(profile)
    if not path.exists():
        return {"version": 1, "refreshed_at": None, "scripts": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Scripts index must be a JSON object: {path}")
    return payload


def save_scripts_index(profile: CredentialProfile, payload: Mapping[str, Any]) -> Path:
    path = scripts_index_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def write_scripts_cache(profile: CredentialProfile, scripts: list[dict[str, Any]]) -> Path:
    payload = {
        "version": 1,
        "profile_slug": profile.slug,
        "cache_key": profile.cache_key,
        "refreshed_at": _utc_now_iso(),
        "count": len(scripts),
        "scripts": scripts,
    }
    return save_scripts_index(profile, payload)


def script_index_maps(profile: CredentialProfile) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return ``(by_id, by_name)`` maps from the scripts cache index."""
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    index = load_scripts_index(profile)
    for item in index.get("scripts") or []:
        if not isinstance(item, dict):
            continue
        script_id = str(item.get("id") or "")
        name = str(item.get("name") or "")
        if script_id:
            by_id[script_id] = item
        if name:
            by_name[name] = item
    return by_id, by_name


def find_script_in_index(
    profile: CredentialProfile,
    *,
    script_id: Optional[str] = None,
    name: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    index = load_scripts_index(profile)
    items = index.get("scripts") or []
    for item in items:
        if not isinstance(item, dict):
            continue
        if script_id and str(item.get("id")) == str(script_id):
            return item
        if name and str(item.get("name")) == name:
            return item
    return None
