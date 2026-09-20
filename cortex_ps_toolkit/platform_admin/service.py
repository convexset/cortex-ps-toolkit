"""Platform admin cache refresh and listing."""

from __future__ import annotations

from typing import Any

from ..credentials import CredentialProfile, get_profile
from ..platforms import UnsupportedOperation
from . import api
from .cache import load_index, list_cached, write_cache
from .types import ADMIN_SECTIONS, AdminSection


def refresh_section_cache(profile: CredentialProfile | str, section: AdminSection) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    items = api.fetch_section_items(resolved, section)
    path = write_cache(resolved, section, items)
    return {
        "profile": resolved.slug,
        "section": section,
        "count": len(items),
        "cache_path": str(path),
        "refreshed_at": load_index(resolved, section).get("refreshed_at"),
    }


def refresh_all_cache(profile: CredentialProfile | str) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    results: dict[str, Any] = {}
    for section in ADMIN_SECTIONS:
        try:
            results[section] = refresh_section_cache(resolved, section)
        except UnsupportedOperation as exc:
            results[section] = {"skipped": True, "reason": str(exc)}
    return {"profile": resolved.slug, "sections": results}


def list_cached_items(profile: CredentialProfile | str, section: AdminSection) -> list[dict[str, Any]]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    return list_cached(resolved, section)
