"""Map source tenant playbook IDs to target tenant IDs after component copy."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ..credentials import CredentialProfile, get_profile
from ..ops_log import op_debug, op_info
from .cache import find_playbook_in_index


def target_playbook_id_after_save(
    target: CredentialProfile,
    *,
    name: str,
    saved: Optional[Mapping[str, Any]] = None,
    fallback_id: Optional[str] = None,
) -> str:
    """Resolve target playbook id after insert or from cache by name."""
    if fallback_id:
        return str(fallback_id)
    if saved:
        for key in ("id", "playbookId"):
            value = saved.get(key)
            if value:
                return str(value)
        objects = saved.get("objects")
        if isinstance(objects, dict):
            for item in objects.get("succeeded_items") or []:
                if isinstance(item, dict) and item.get("id"):
                    return str(item["id"])
    entry = find_playbook_in_index(target, name=name)
    if entry and entry.get("id"):
        return str(entry["id"])
    return ""


def seed_playbook_id_remap(plan_playbook_items: list[dict[str, Any]]) -> dict[str, str]:
    """Pre-seed remap from plan items that already have a target id (skip/update)."""
    remap: dict[str, str] = {}
    for item in plan_playbook_items:
        source_id = str(item.get("playbook_id") or "")
        target_id = str(item.get("target_id") or "")
        if source_id and target_id:
            remap[source_id] = target_id
    return remap


def register_playbook_remap_entry(
    remap: dict[str, str],
    *,
    source_id: str,
    target_id: str,
    name: str,
    target: CredentialProfile | str,
) -> None:
    """Record one source→target playbook mapping and log it."""
    if not source_id or not target_id:
        return
    remap[source_id] = target_id
    op_debug("Playbook remap %s → %s (%s)", source_id, target_id, name)


def log_playbook_remap_summary(remap: Mapping[str, str], target: CredentialProfile | str) -> None:
    resolved = get_profile(target) if isinstance(target, str) else target
    if remap:
        op_info(
            "Playbook id remap on %s: %d entr%s",
            resolved.slug,
            len(remap),
            "y" if len(remap) == 1 else "ies",
        )
