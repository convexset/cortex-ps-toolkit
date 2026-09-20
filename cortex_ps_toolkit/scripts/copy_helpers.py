"""Helpers for script copy result handling."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ..credentials import CredentialProfile
from .cache import find_script_in_index


def target_script_id_after_save(
    target: CredentialProfile,
    *,
    name: str,
    saved: Optional[Mapping[str, Any]] = None,
    fallback_id: Optional[str] = None,
) -> str:
    """Resolve the target script id after insert or from cache by name."""
    if fallback_id:
        return str(fallback_id)
    if saved:
        for key in ("id", "scriptId"):
            value = saved.get(key)
            if value:
                return str(value)
        objects = saved.get("objects")
        if isinstance(objects, dict):
            for item in objects.get("succeeded_items") or []:
                if isinstance(item, dict) and item.get("id"):
                    return str(item["id"])
    entry = find_script_in_index(target, name=name)
    if entry and entry.get("id"):
        return str(entry["id"])
    return ""
