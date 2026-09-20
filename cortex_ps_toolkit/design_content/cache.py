"""On-disk cache for design-time content assets."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from ..credentials import CredentialProfile
from ..paths import cache_root
from .types import AssetKind


def design_cache_dir(profile: CredentialProfile) -> Path:
    return cache_root() / profile.cache_key / "design_content"


def index_path(profile: CredentialProfile, asset: AssetKind) -> Path:
    return design_cache_dir(profile) / asset / "index.json"


def body_path(profile: CredentialProfile, asset: AssetKind, item_id: str) -> Path:
    safe = item_id.replace("/", "_")
    return design_cache_dir(profile) / asset / "bodies" / f"{safe}.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_index(profile: CredentialProfile, asset: AssetKind) -> dict[str, Any]:
    path = index_path(profile, asset)
    if not path.exists():
        return {"version": 1, "asset": asset, "refreshed_at": None, "items": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Design content index must be object: {path}")
    return payload


def save_index(profile: CredentialProfile, asset: AssetKind, payload: Mapping[str, Any]) -> Path:
    path = index_path(profile, asset)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def write_cache(
    profile: CredentialProfile,
    asset: AssetKind,
    items: list[dict[str, Any]],
    *,
    store_bodies: bool = True,
) -> Path:
    summaries: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or item.get("name") or "")
        if store_bodies and item_id:
            path = body_path(profile, asset, item_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(item, indent=2) + "\n", encoding="utf-8")
        summaries.append({
            "id": item.get("id"),
            "name": item.get("name"),
            "type": item.get("type"),
            "packID": item.get("packID"),
            "modified": item.get("modified"),
        })
    payload = {
        "version": 1,
        "asset": asset,
        "profile_slug": profile.slug,
        "cache_key": profile.cache_key,
        "refreshed_at": _utc_now_iso(),
        "count": len(summaries),
        "items": summaries,
    }
    return save_index(profile, asset, payload)


def list_cached(profile: CredentialProfile, asset: AssetKind) -> list[dict[str, Any]]:
    index = load_index(profile, asset)
    return [item for item in (index.get("items") or []) if isinstance(item, dict)]


def find_in_index(
    profile: CredentialProfile,
    asset: AssetKind,
    *,
    item_id: Optional[str] = None,
    name: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    for item in list_cached(profile, asset):
        if item_id and str(item.get("id")) == str(item_id):
            return item
        if name and str(item.get("name")) == name:
            return item
    return None


def load_body(profile: CredentialProfile, asset: AssetKind, item_id: str) -> Optional[dict[str, Any]]:
    path = body_path(profile, asset, item_id)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None

