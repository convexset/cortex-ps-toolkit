"""Script origin metadata: system vs custom vs content-pack owned."""

from __future__ import annotations

import re
from typing import Any, Literal, Mapping, Optional

from ..credentials import CredentialProfile, get_profile
from . import api
from .cache import find_script_in_index
from .delete import is_system_script

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

ScriptOrigin = Literal["system", "content_pack", "custom"]


def looks_like_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(str(value or "").strip()))


def pack_id_from_document(document: Mapping[str, Any]) -> str:
    for key in ("packID", "packId", "packid"):
        value = document.get(key)
        if value:
            return str(value)
    return ""


def pack_name_from_document(document: Mapping[str, Any]) -> str:
    for key in ("packName", "packname"):
        value = document.get(key)
        if value:
            return str(value)
    return ""


def classify_script_entry(
    entry: Mapping[str, Any],
    *,
    document: Optional[Mapping[str, Any]] = None,
) -> ScriptOrigin:
    """Classify a script from cache index and optional full tenant document."""
    if is_system_script(entry) or (document and is_system_script(document)):
        return "system"
    doc = document or entry
    if pack_id_from_document(doc):
        return "content_pack"
    script_id = str(entry.get("id") or doc.get("id") or "")
    if script_id and not looks_like_uuid(script_id):
        return "content_pack"
    return "custom"


def is_copyable_script(
    entry: Mapping[str, Any],
    *,
    document: Optional[Mapping[str, Any]] = None,
) -> bool:
    """Return True when a script is tenant/custom content worth copying."""
    return classify_script_entry(entry, document=document) == "custom"


def describe_script(
    profile: CredentialProfile | str,
    *,
    script_id: Optional[str] = None,
    name: Optional[str] = None,
    load_document: bool = False,
) -> dict[str, Any]:
    """Describe one script from cache; optionally load full document for pack metadata."""
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    entry = find_script_in_index(resolved, script_id=script_id, name=name)
    if not entry:
        return {
            "profile": resolved.slug,
            "found": False,
            "script_id": script_id,
            "name": name,
        }

    document: Optional[dict[str, Any]] = None
    if load_document:
        lookup_id = str(script_id or entry.get("id") or name or "")
        document = api.get_script(resolved, lookup_id)

    origin = classify_script_entry(entry, document=document)
    result: dict[str, Any] = {
        "profile": resolved.slug,
        "found": True,
        "script_id": entry.get("id"),
        "name": entry.get("name"),
        "origin": origin,
        "system": is_system_script(entry) or (document and is_system_script(document)),
        "copyable": origin == "custom",
        "cache": {
            "modified": entry.get("modified"),
            "scriptType": entry.get("scriptType"),
            "version": entry.get("version"),
            "description": entry.get("description"),
        },
    }
    if document:
        result["document"] = {
            "packID": pack_id_from_document(document),
            "packName": pack_name_from_document(document),
            "isInternal": document.get("isInternal"),
            "locked": document.get("locked"),
            "dockerImage": document.get("dockerImage") or document.get("dockerimage"),
            "type": document.get("type"),
            "subtype": document.get("subtype"),
        }
        if load_document and result["document"].get("packID"):
            result["origin"] = classify_script_entry(entry, document=document)
            result["copyable"] = result["origin"] == "custom"
    return result
