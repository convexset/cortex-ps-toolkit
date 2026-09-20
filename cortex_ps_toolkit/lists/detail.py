"""List detail payloads for the web viewer."""

from __future__ import annotations

from typing import Any

from ..credentials import CredentialProfile, get_profile
from .cache import find_list_in_index
from .copy import normalize_list_data, resolve_list_entry
from .service import refresh_lists_cache


def split_list_document(document: dict[str, Any]) -> tuple[dict[str, Any], str]:
    doc = dict(document)
    data_text = normalize_list_data(doc.pop("data", None), "")
    return doc, data_text


def _find_list_entry(profile: CredentialProfile, list_id: str) -> dict[str, Any]:
    needle = str(list_id)
    entry = find_list_in_index(profile, list_id=needle)
    if entry is None:
        entry = find_list_in_index(profile, name=needle)
    if entry is None:
        refresh_lists_cache(profile)
        entry = find_list_in_index(profile, list_id=needle)
        if entry is None:
            entry = find_list_in_index(profile, name=needle)
    if entry is None:
        raise KeyError(f"List not found: {list_id}")
    return dict(entry)


def get_list_detail(profile: CredentialProfile | str, list_id: str) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    entry = _find_list_entry(resolved, list_id)
    full = resolve_list_entry(resolved, str(entry.get("id") or list_id))
    configuration, data_text = split_list_document(full)
    return {
        "profile": resolved.slug,
        "id": str(configuration.get("id") or list_id),
        "name": str(configuration.get("name") or ""),
        "kind": "list",
        "configuration": configuration,
        "data": data_text,
        "list_type": str(configuration.get("type") or ""),
    }
