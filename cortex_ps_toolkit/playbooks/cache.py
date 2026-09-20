"""On-disk playbook cache under data/cache/{cache_key}/playbooks/."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from ..credentials import CredentialProfile
from ..paths import cache_root


def playbooks_cache_dir(profile: CredentialProfile) -> Path:
    return cache_root() / profile.cache_key / "playbooks"


def playbooks_index_path(profile: CredentialProfile) -> Path:
    return playbooks_cache_dir(profile) / "index.json"


def playbooks_bodies_dir(profile: CredentialProfile) -> Path:
    return playbooks_cache_dir(profile) / "bodies"


def playbook_body_path(profile: CredentialProfile, playbook_id: str) -> Path:
    safe_id = str(playbook_id).replace("/", "_")
    return playbooks_bodies_dir(profile) / f"{safe_id}.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_playbooks_index(profile: CredentialProfile) -> dict[str, Any]:
    path = playbooks_index_path(profile)
    if not path.exists():
        return {"version": 1, "refreshed_at": None, "playbooks": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Playbooks index must be a JSON object: {path}")
    return payload


def save_playbooks_index(profile: CredentialProfile, payload: Mapping[str, Any]) -> Path:
    path = playbooks_index_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def write_playbooks_cache(profile: CredentialProfile, playbooks: list[dict[str, Any]]) -> Path:
    payload = {
        "version": 1,
        "profile_slug": profile.slug,
        "cache_key": profile.cache_key,
        "refreshed_at": _utc_now_iso(),
        "count": len(playbooks),
        "playbooks": playbooks,
    }
    return save_playbooks_index(profile, payload)


def load_playbook_body(profile: CredentialProfile, playbook_id: str) -> Optional[dict[str, Any]]:
    """Return cached playbook document when present and index modified stamp still matches."""
    path = playbook_body_path(profile, playbook_id)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    playbook = payload.get("playbook")
    if not isinstance(playbook, dict):
        return None
    index_meta = find_playbook_in_index(profile, playbook_id=playbook_id)
    cached_modified = payload.get("modified")
    index_modified = (index_meta or {}).get("modified")
    if index_meta and cached_modified != index_modified:
        return None
    return playbook


def save_playbook_body(profile: CredentialProfile, playbook_id: str, playbook: Mapping[str, Any]) -> Path:
    index_meta = find_playbook_in_index(profile, playbook_id=playbook_id)
    path = playbook_body_path(profile, playbook_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": playbook_id,
        "modified": (index_meta or {}).get("modified"),
        "cached_at": _utc_now_iso(),
        "playbook": dict(playbook),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def find_playbook_in_index(
    profile: CredentialProfile,
    *,
    playbook_id: Optional[str] = None,
    name: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    index = load_playbooks_index(profile)
    items = index.get("playbooks") or []
    for item in items:
        if not isinstance(item, dict):
            continue
        if playbook_id and str(item.get("id")) == str(playbook_id):
            return item
        if name and str(item.get("name")) == name:
            return item
    return None
