"""Built-in and user-saved XQL query presets."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Mapping, Optional

from ..collections import load_collection, save_collection
from ..paths import collections_dir, package_root

BUILTIN_PRESETS_PATH = package_root() / "presets" / "xql" / "builtin-presets.json"
USER_PRESETS_PATH = collections_dir() / "xql_presets.json"


def _default_user_presets() -> dict[str, Any]:
    return {"version": 1, "presets": []}


def load_builtin_presets() -> dict[str, Any]:
    if not BUILTIN_PRESETS_PATH.exists():
        return {"version": 1, "presets": {}}
    payload = json.loads(BUILTIN_PRESETS_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid builtin presets file: {BUILTIN_PRESETS_PATH}")
    return payload


def list_builtin_presets() -> list[dict[str, Any]]:
    payload = load_builtin_presets()
    presets = payload.get("presets") or {}
    rows: list[dict[str, Any]] = []
    if isinstance(presets, dict):
        for key, item in presets.items():
            if isinstance(item, dict):
                rows.append({"id": key, "source": "builtin", **item})
    return rows


def load_user_presets() -> dict[str, Any]:
    payload = load_collection(USER_PRESETS_PATH, default=_default_user_presets())
    payload.setdefault("version", 1)
    payload.setdefault("presets", [])
    return payload


def list_user_presets() -> list[dict[str, Any]]:
    items = load_user_presets().get("presets") or []
    rows: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict) and item.get("id"):
            rows.append({"source": "user", **item})
    return rows


def save_user_preset(
    *,
    name: str,
    query: str,
    timeframe_ms: Optional[str] = None,
    query_name: Optional[str] = None,
    preset_id: Optional[str] = None,
) -> dict[str, Any]:
    payload = load_user_presets()
    presets = [item for item in (payload.get("presets") or []) if isinstance(item, dict)]
    entry = {
        "id": preset_id or str(uuid.uuid4()),
        "name": name.strip(),
        "query": query,
        "timeframe_ms": timeframe_ms,
        "query_name": query_name or name.strip(),
    }
    replaced = False
    for index, existing in enumerate(presets):
        if str(existing.get("id")) == entry["id"]:
            presets[index] = entry
            replaced = True
            break
    if not replaced:
        presets.append(entry)
    payload["presets"] = presets
    save_collection(USER_PRESETS_PATH, payload)
    return {"source": "user", **entry}


def delete_user_preset(preset_id: str) -> bool:
    payload = load_user_presets()
    presets = [item for item in (payload.get("presets") or []) if isinstance(item, dict)]
    kept = [item for item in presets if str(item.get("id")) != preset_id]
    if len(kept) == len(presets):
        return False
    payload["presets"] = kept
    save_collection(USER_PRESETS_PATH, payload)
    return True
