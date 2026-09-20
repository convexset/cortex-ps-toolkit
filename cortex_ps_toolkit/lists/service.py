"""Lists cache refresh and CRUD orchestration."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ..credentials import CredentialProfile, get_profile
from . import api
from .cache import find_list_in_index, load_lists_index, write_lists_cache


def refresh_lists_cache(profile: CredentialProfile | str) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    lists = api.fetch_all_lists(resolved)
    path = write_lists_cache(resolved, lists)
    return {
        "profile": resolved.slug,
        "count": len(lists),
        "cache_path": str(path),
        "refreshed_at": load_lists_index(resolved).get("refreshed_at"),
    }


def list_cached_lists(profile: CredentialProfile | str) -> list[dict[str, Any]]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    index = load_lists_index(resolved)
    items = index.get("lists") or []
    return [item for item in items if isinstance(item, dict)]


def get_list_by_name(profile: CredentialProfile | str, name: str) -> Optional[dict[str, Any]]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    cached = find_list_in_index(resolved, name=name)
    if cached:
        return cached
    refresh_lists_cache(resolved)
    return find_list_in_index(resolved, name=name)


def save_list(
    profile: CredentialProfile | str,
    *,
    name: str,
    data: str,
    list_type: str = "plain_text",
    description: str = "",
    list_id: Optional[str] = None,
) -> tuple[dict[str, Any], int]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    if list_id:
        existing = find_list_in_index(resolved, list_id=list_id)
        if not existing:
            refresh_lists_cache(resolved)
            existing = find_list_in_index(resolved, list_id=list_id)
        if not existing:
            raise KeyError(f"List id not found in cache: {list_id}")
        payload = api.build_update_list_payload(
            existing,
            {"name": name, "data": data, "type": list_type, "description": description},
        )
    else:
        existing = find_list_in_index(resolved, name=name)
        if existing:
            payload = api.build_update_list_payload(
                existing,
                {"name": name, "data": data, "type": list_type, "description": description},
            )
        else:
            payload = api.build_new_list_payload(
                name=name,
                data=data,
                list_type=list_type,
                description=description,
            )
    saved, status_code = api.save_list_payload(resolved, payload)
    refresh_lists_cache(resolved)
    return saved, status_code


def delete_list(profile: CredentialProfile | str, *, list_id: str) -> tuple[Any, int]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    result, status_code = api.delete_list_by_id(resolved, list_id)
    refresh_lists_cache(resolved)
    return result, status_code
