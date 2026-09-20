"""On-disk lists cache under data/cache/{cache_key}/lists/."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from ..credentials import CredentialProfile
from ..paths import cache_root


def lists_cache_dir(profile: CredentialProfile) -> Path:
    return cache_root() / profile.cache_key / "lists"


def lists_index_path(profile: CredentialProfile) -> Path:
    return lists_cache_dir(profile) / "index.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_lists_index(profile: CredentialProfile) -> dict[str, Any]:
    path = lists_index_path(profile)
    if not path.exists():
        return {"version": 1, "refreshed_at": None, "lists": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Lists index must be a JSON object: {path}")
    return payload


def save_lists_index(profile: CredentialProfile, payload: Mapping[str, Any]) -> Path:
    path = lists_index_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def write_lists_cache(profile: CredentialProfile, lists: list[dict[str, Any]]) -> Path:
    payload = {
        "version": 1,
        "profile_slug": profile.slug,
        "cache_key": profile.cache_key,
        "refreshed_at": _utc_now_iso(),
        "count": len(lists),
        "lists": lists,
    }
    return save_lists_index(profile, payload)


def find_list_in_index(
    profile: CredentialProfile,
    *,
    list_id: Optional[str] = None,
    name: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    index = load_lists_index(profile)
    items = index.get("lists") or []
    for item in items:
        if not isinstance(item, dict):
            continue
        if list_id and str(item.get("id")) == str(list_id):
            return item
        if name and str(item.get("name")) == name:
            return item
    return None
