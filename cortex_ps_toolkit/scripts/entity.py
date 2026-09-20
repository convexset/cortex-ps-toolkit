"""Script document identity helpers (XSOAR vs XSIAM shapes)."""

from __future__ import annotations

from typing import Any, Mapping


def script_entity_id(document: Mapping[str, Any]) -> str:
    """Return tenant script id from API JSON or XSIAM YAML-loaded dict."""
    top_level = document.get("id")
    if top_level:
        return str(top_level)
    common = document.get("commonfields")
    if isinstance(common, dict) and common.get("id"):
        return str(common["id"])
    return ""
