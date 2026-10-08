"""Pack-style ``contentitemexportablefields`` blocks for portable YAML exports."""

from __future__ import annotations

from typing import Any, Mapping


def content_item_export_block(source: Mapping[str, Any]) -> dict[str, Any] | None:
    """Build block present on XSOAR 6 pack / tenant UI exports when pack metadata exists."""
    pack_id = str(source.get("packID") or source.get("packId") or "").strip()
    pack_name = str(source.get("packName") or "").strip()
    item_version = str(source.get("itemVersion") or "").strip()
    from_server = str(source.get("fromServerVersion") or "").strip()
    if not pack_id and not pack_name and not item_version and not from_server:
        return None
    return {
        "contentitemexportablefields": {
            "contentitemfields": {
                "packID": pack_id,
                "packName": pack_name,
                "itemVersion": item_version,
                "fromServerVersion": from_server,
                "toServerVersion": str(source.get("toServerVersion") or ""),
                "definitionid": str(source.get("definitionId") or source.get("definitionid") or ""),
                "prevname": str(source.get("prevName") or source.get("prevname") or ""),
            },
        },
    }


def merge_export_document(*sections: dict[str, Any] | None) -> dict[str, Any]:
    """Merge export sections preserving typical field order."""
    out: dict[str, Any] = {}
    for section in sections:
        if section:
            out.update(section)
    return out
