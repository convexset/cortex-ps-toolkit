"""Persist saved visual specs (toolkit data/collections)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ...collections import load_collection, save_collection
from ...paths import collections_dir
from .spec import VisualSpec

COLLECTION_NAME = "xql_visualizations.json"


def _path():
    return collections_dir() / COLLECTION_NAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def list_saved_visualizations(*, profile: Optional[str] = None) -> list[dict[str, Any]]:
    payload = load_collection(_path(), default={"version": 1, "visualizations": []})
    items = payload.get("visualizations") or []
    if not isinstance(items, list):
        return []
    out = [item for item in items if isinstance(item, dict)]
    if profile:
        out = [item for item in out if str(item.get("profile") or "") == profile]
    return out


def save_visualization(
    *,
    spec: VisualSpec,
    label: str,
    profile: str,
    visualization_id: Optional[str] = None,
    query_id: Optional[str] = None,
    columns_fingerprint: Optional[list[str]] = None,
) -> dict[str, Any]:
    payload = load_collection(_path(), default={"version": 1, "visualizations": []})
    items = list(payload.get("visualizations") or [])
    vid = visualization_id or f"viz_{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    record = {
        "id": vid,
        "label": label or spec.label or spec.title or "Chart",
        "profile": profile,
        "query_id": query_id,
        "columns_fingerprint": columns_fingerprint or [],
        "spec": spec.to_dict(),
        "updated_at": now,
    }
    replaced = False
    for index, item in enumerate(items):
        if isinstance(item, dict) and item.get("id") == vid:
            record["created_at"] = item.get("created_at") or now
            items[index] = record
            replaced = True
            break
    if not replaced:
        record["created_at"] = now
        items.append(record)
    payload["visualizations"] = items
    save_collection(_path(), payload)
    return record


def delete_visualization(visualization_id: str) -> bool:
    payload = load_collection(_path(), default={"version": 1, "visualizations": []})
    items = list(payload.get("visualizations") or [])
    kept = [item for item in items if not (isinstance(item, dict) and item.get("id") == visualization_id)]
    if len(kept) == len(items):
        return False
    payload["visualizations"] = kept
    save_collection(_path(), payload)
    return True
