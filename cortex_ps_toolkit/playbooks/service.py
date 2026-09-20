"""Playbook cache refresh orchestration."""

from __future__ import annotations

from typing import Any, Optional

from ..credentials import CredentialProfile, get_profile
from ..ops_log import op_info
from . import api
from .cache import find_playbook_in_index, load_playbooks_index, write_playbooks_cache


def refresh_playbooks_cache(profile: CredentialProfile | str) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    op_info("Fetching playbooks from tenant API for %s", resolved.slug)
    playbooks_raw = api.search_playbooks(resolved)
    playbooks = [api.cache_entry_from_search(item) for item in playbooks_raw if item.get("id")]
    path = write_playbooks_cache(resolved, playbooks)
    return {
        "profile": resolved.slug,
        "count": len(playbooks),
        "cache_path": str(path),
        "refreshed_at": load_playbooks_index(resolved).get("refreshed_at"),
    }


def list_cached_playbooks(profile: CredentialProfile | str) -> list[dict[str, Any]]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    index = load_playbooks_index(resolved)
    items = index.get("playbooks") or []
    return [item for item in items if isinstance(item, dict)]


def get_playbook_by_name(profile: CredentialProfile | str, name: str) -> Optional[dict[str, Any]]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    cached = find_playbook_in_index(resolved, name=name)
    if cached:
        return cached
    refresh_playbooks_cache(resolved)
    return find_playbook_in_index(resolved, name=name)
