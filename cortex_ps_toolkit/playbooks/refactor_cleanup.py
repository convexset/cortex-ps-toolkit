"""Delete generated [REFACTOR-*] playbooks from a tenant."""

from __future__ import annotations

import time
from typing import Any, Optional

from ..credentials import get_profile
from .delete import delete_playbooks
from .service import list_cached_playbooks, refresh_playbooks_cache


def find_refactor_playbook_ids(
    profile_slug: str,
    *,
    name_prefix: str = "[REFACTOR-",
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    profile = get_profile(profile_slug)
    if force_refresh:
        refresh_playbooks_cache(profile)
    matches: list[dict[str, Any]] = []
    for item in list_cached_playbooks(profile):
        name = str(item.get("name") or "")
        if name.startswith(name_prefix):
            matches.append({
                "id": str(item.get("id") or ""),
                "name": name,
            })
    return matches


def clear_refactor_playbooks(
    profile_slug: str,
    *,
    name_prefix: str = "[REFACTOR-",
    force_refresh: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Remove all playbooks whose names start with *name_prefix*."""
    started = time.monotonic()
    matches = find_refactor_playbook_ids(
        profile_slug,
        name_prefix=name_prefix,
        force_refresh=force_refresh,
    )
    if dry_run:
        return {
            "profile": profile_slug,
            "dry_run": True,
            "name_prefix": name_prefix,
            "matched": matches,
            "count": len(matches),
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }

    if not matches:
        return {
            "profile": profile_slug,
            "name_prefix": name_prefix,
            "matched": [],
            "delete_result": {"counts": {"deleted": 0, "total": 0}},
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }

    delete_result = delete_playbooks(profile_slug, [row["id"] for row in matches if row.get("id")])
    return {
        "profile": profile_slug,
        "name_prefix": name_prefix,
        "matched": matches,
        "delete_result": delete_result,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }
