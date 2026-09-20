"""Script cache refresh orchestration."""

from __future__ import annotations

from typing import Any, Optional

from ..credentials import CredentialProfile, get_profile
from ..ops_log import op_info
from . import api
from .cache import find_script_in_index, load_scripts_index, scripts_index_path, write_scripts_cache


def refresh_scripts_cache(profile: CredentialProfile | str) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    op_info("Fetching scripts from tenant API for %s", resolved.slug)
    search = api.search_scripts(resolved)

    if search.warning and not search.scripts:
        index = load_scripts_index(resolved)
        existing = [item for item in (index.get("scripts") or []) if isinstance(item, dict)]
        if existing:
            return {
                "profile": resolved.slug,
                "count": len(existing),
                "cache_path": str(scripts_index_path(resolved)),
                "refreshed_at": index.get("refreshed_at"),
                "warning": search.warning,
                "cache_preserved": True,
                "search_endpoint": search.endpoint,
                "status_code": search.status_code,
            }

    scripts = [api.cache_entry_from_search(item) for item in search.scripts if item.get("id")]
    path = write_scripts_cache(resolved, scripts)
    result: dict[str, Any] = {
        "profile": resolved.slug,
        "count": len(scripts),
        "cache_path": str(path),
        "refreshed_at": load_scripts_index(resolved).get("refreshed_at"),
        "search_endpoint": search.endpoint,
    }
    if search.status_code is not None:
        result["status_code"] = search.status_code
    if search.compat_mode:
        result["compat_mode"] = True
    if search.warning:
        result["warning"] = search.warning
    return result


def list_cached_scripts(profile: CredentialProfile | str) -> list[dict[str, Any]]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    index = load_scripts_index(resolved)
    items = index.get("scripts") or []
    return [item for item in items if isinstance(item, dict)]


def get_script_by_name(profile: CredentialProfile | str, name: str) -> Optional[dict[str, Any]]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    cached = find_script_in_index(resolved, name=name)
    if cached:
        return cached
    refresh_scripts_cache(resolved)
    return find_script_in_index(resolved, name=name)
