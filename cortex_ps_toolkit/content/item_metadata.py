"""Shared system/pack metadata for scripts and playbooks."""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional

from ..scripts.delete import is_system_script
from ..scripts.metadata import (
    classify_script_entry,
    is_copyable_script,
    pack_id_from_document,
    pack_name_from_document,
)

ContentOrigin = Literal["system", "content_pack", "custom"]


def item_metadata_row(
    *,
    cache_entry: Optional[Mapping[str, Any]] = None,
    document: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Build a normalized metadata row from cache index and/or full document."""
    entry = dict(cache_entry or {})
    doc = document or entry
    system = is_system_script(entry) or is_system_script(doc)
    pack_id = pack_id_from_document(doc)
    pack_name = pack_name_from_document(doc)
    origin: ContentOrigin
    if system:
        origin = "system"
    elif pack_id:
        origin = "content_pack"
    else:
        item_id = str(entry.get("id") or doc.get("id") or "")
        if item_id and not _looks_like_uuid(item_id):
            origin = "content_pack"
        else:
            origin = "custom"
    copyable = origin == "custom"
    return {
        "system": system,
        "origin": origin,
        "pack_id": pack_id or None,
        "pack_name": pack_name or None,
        "copyable": copyable,
    }


def script_metadata_row(
    *,
    cache_entry: Optional[Mapping[str, Any]] = None,
    document: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    row = item_metadata_row(cache_entry=cache_entry, document=document)
    if cache_entry or document:
        row["origin"] = classify_script_entry(cache_entry or {}, document=document)
        row["copyable"] = is_copyable_script(cache_entry or {}, document=document)
        if document:
            row["pack_id"] = pack_id_from_document(document) or row.get("pack_id")
            row["pack_name"] = pack_name_from_document(document) or row.get("pack_name")
    return row


def _looks_like_uuid(value: str) -> bool:
    import re

    return bool(
        re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            str(value or "").strip(),
            re.IGNORECASE,
        )
    )
