"""Saved Object Setup bundles scoped by source tenant profile."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from ..collections import load_collection, save_collection
from ..credentials import get_profile
from ..paths import collections_dir
from ..platform_admin.service import list_cached_items as list_admin_cached_items
from .service import list_cached_items
from .types import ASSET_KINDS, AssetKind

BUNDLES_PATH = collections_dir() / "object_setup_bundles.json"
CORRELATION_ASSET = "correlation-rules"
_BUNDLE_ID_MAX_LEN = 120


def _default_store() -> dict[str, Any]:
    return {"version": 2, "profiles": {}}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_bundle_id(name: str) -> str:
    """Single stable identifier for a bundle within one source profile."""
    slug = re.sub(r"[^\w./-]+", "-", name.strip()).strip("-./")
    if not slug:
        raise ValueError("bundle identifier required")
    if len(slug) > _BUNDLE_ID_MAX_LEN:
        slug = slug[:_BUNDLE_ID_MAX_LEN].rstrip("-./")
    if not slug:
        raise ValueError("bundle identifier required")
    return slug


def _migrate_store(raw: dict[str, Any]) -> dict[str, Any]:
    if int(raw.get("version") or 0) >= 2 and isinstance(raw.get("profiles"), dict):
        return raw

    profiles: dict[str, dict[str, Any]] = {}
    for item in raw.get("bundles") or []:
        if not isinstance(item, dict):
            continue
        prof = str(item.get("source_profile") or "").strip()
        if not prof:
            continue
        display = str(item.get("name") or item.get("application") or "").strip()
        legacy_id = str(item.get("id") or "").strip()
        try:
            bundle_id = legacy_id if legacy_id else normalize_bundle_id(display or "bundle")
        except ValueError:
            continue
        entry = {
            "id": bundle_id,
            "name": display or bundle_id,
            "source_profile": prof,
            "items": list(item.get("items") or []),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }
        profiles.setdefault(prof, {})[bundle_id] = entry

    return {"version": 2, "profiles": profiles}


def load_bundles_store() -> dict[str, Any]:
    payload = load_collection(BUNDLES_PATH, default=_default_store())
    migrated = _migrate_store(payload if isinstance(payload, dict) else _default_store())
    if migrated is not payload:
        save_collection(BUNDLES_PATH, migrated)
    return migrated


def _profile_bundles(store: dict[str, Any], source_profile: str) -> dict[str, Any]:
    profiles = store.get("profiles") or {}
    bucket = profiles.get(source_profile)
    if not isinstance(bucket, dict):
        return {}
    return bucket


def list_bundle_presets(*, source_profile: str) -> list[dict[str, Any]]:
    prof = source_profile.strip()
    if not prof:
        raise ValueError("source_profile required")
    bucket = _profile_bundles(load_bundles_store(), prof)
    rows = [dict(item) for item in bucket.values() if isinstance(item, dict) and item.get("id")]
    rows.sort(key=lambda row: str(row.get("name") or row.get("id") or "").lower())
    return rows


def get_bundle_preset(source_profile: str, bundle_id: str) -> dict[str, Any]:
    prof = source_profile.strip()
    bid = bundle_id.strip()
    if not prof or not bid:
        raise KeyError(bundle_id)
    entry = _profile_bundles(load_bundles_store(), prof).get(bid)
    if not entry:
        raise KeyError(bundle_id)
    return dict(entry)


def save_bundle_preset(
    *,
    name: str,
    source_profile: str,
    items: list[dict[str, Any]],
    bundle_id: Optional[str] = None,
    application: Optional[str] = None,
) -> dict[str, Any]:
    """Save bundle under *source_profile*; identifier is normalized *name* unless *bundle_id* set."""
    del application  # legacy API field — identifier is name/id only
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("name required")
    if not source_profile.strip():
        raise ValueError("source_profile required")
    if not items:
        raise ValueError("items required")

    normalized_items: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        asset = str(raw.get("asset") or "").strip()
        item_id = str(raw.get("id") or raw.get("name") or "").strip()
        item_name = str(raw.get("name") or item_id).strip()
        if not asset or not item_id:
            continue
        normalized_items.append(
            {
                "asset": asset,
                "id": item_id,
                "name": item_name,
                "type": str(raw.get("type") or asset),
            },
        )
    if not normalized_items:
        raise ValueError("items required")

    profile = get_profile(source_profile)
    prof_slug = profile.slug
    entry_id = normalize_bundle_id(bundle_id or clean_name)
    now = _now_iso()

    store = load_bundles_store()
    profiles = store.setdefault("profiles", {})
    bucket = profiles.setdefault(prof_slug, {})
    existing = bucket.get(entry_id) if isinstance(bucket, dict) else None

    entry = {
        "id": entry_id,
        "name": clean_name,
        "source_profile": prof_slug,
        "items": normalized_items,
        "updated_at": now,
        "created_at": (existing or {}).get("created_at") or now,
    }
    if not isinstance(bucket, dict):
        bucket = {}
        profiles[prof_slug] = bucket
    bucket[entry_id] = entry
    store["version"] = 2
    save_collection(BUNDLES_PATH, store)
    return entry


def delete_bundle_preset(source_profile: str, bundle_id: str) -> bool:
    prof = source_profile.strip()
    bid = bundle_id.strip()
    if not prof or not bid:
        return False
    store = load_bundles_store()
    profiles = store.get("profiles") or {}
    bucket = profiles.get(prof)
    if not isinstance(bucket, dict) or bid not in bucket:
        return False
    del bucket[bid]
    if not bucket:
        profiles.pop(prof, None)
    save_collection(BUNDLES_PATH, store)
    return True


def _match_design_item(
    cached: list[dict[str, Any]],
    *,
    item_id: str,
    item_name: str,
) -> Optional[dict[str, Any]]:
    id_lower = item_id.lower()
    name_lower = item_name.lower()
    for row in cached:
        row_id = str(row.get("id") or "")
        row_name = str(row.get("name") or "")
        if row_id and row_id == item_id:
            return row
        if row_id.lower() == id_lower:
            return row
    for row in cached:
        row_name = str(row.get("name") or "")
        if row_name and row_name.lower() == name_lower:
            return row
    return None


def resolve_bundle_items(profile: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Map saved bundle entries to ids on the given source profile (id first, then name)."""
    resolved = get_profile(profile)
    design_cache: dict[str, list[dict[str, Any]]] = {}
    output: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for raw in items:
        if not isinstance(raw, dict):
            continue
        asset = str(raw.get("asset") or "").strip()
        saved_id = str(raw.get("id") or "").strip()
        saved_name = str(raw.get("name") or saved_id).strip()
        if not asset or not saved_name:
            continue

        if asset == CORRELATION_ASSET:
            cached = list_admin_cached_items(resolved, CORRELATION_ASSET)  # type: ignore[arg-type]
            match = _match_design_item(
                [{"id": row.get("name"), "name": row.get("name")} for row in cached],
                item_id=saved_id,
                item_name=saved_name,
            )
            if match:
                name = str(match.get("name") or saved_name)
                output.append(
                    {
                        "asset": asset,
                        "id": name,
                        "name": name,
                        "type": raw.get("type") or "Correlation rule",
                        "resolved": True,
                    },
                )
            else:
                missing.append({"asset": asset, "id": saved_id, "name": saved_name})
            continue

        if asset not in ASSET_KINDS:
            missing.append({"asset": asset, "id": saved_id, "name": saved_name})
            continue

        if asset not in design_cache:
            design_cache[asset] = list_cached_items(resolved, asset)  # type: ignore[arg-type]
        match = _match_design_item(design_cache[asset], item_id=saved_id, item_name=saved_name)
        if match:
            output.append(
                {
                    "asset": asset,
                    "id": str(match.get("id") or saved_id),
                    "name": str(match.get("name") or saved_name),
                    "type": str(match.get("type") or raw.get("type") or asset),
                    "resolved": True,
                },
            )
        else:
            missing.append({"asset": asset, "id": saved_id, "name": saved_name})

    return {
        "profile": resolved.slug,
        "items": output,
        "missing": missing,
        "resolved_count": len(output),
        "missing_count": len(missing),
    }
