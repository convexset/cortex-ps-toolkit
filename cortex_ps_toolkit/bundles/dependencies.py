"""Playbook dependency analysis for bundle membership."""

from __future__ import annotations

from typing import Any, Sequence

from ..cache.ensure import check_analysis_caches
from ..credentials import get_profile
from ..playbooks.analysis import analyze_playbook
from ..playbooks.resolver import CachePlaybookResolver
from ..scripts.cache import find_script_in_index
from ..scripts.metadata import classify_script_entry, is_copyable_script


def _basket_keys(items: Sequence[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for row in items:
        asset = str(row.get("asset") or "")
        item_id = str(row.get("id") or "")
        if asset and item_id:
            keys.add(f"{asset}:{item_id}")
    return keys


def plan_playbook_bundle_dependencies(
    source_profile: str,
    playbook_ids: Sequence[str],
    *,
    basket_items: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    profile = get_profile(source_profile)
    check_analysis_caches(profile)
    basket = _basket_keys(basket_items)
    resolver = CachePlaybookResolver(profile, allow_live_fetch=True)
    dependencies: list[dict[str, Any]] = []

    for playbook_id in playbook_ids:
        analysis = analyze_playbook(
            profile.slug,
            playbook_id,
            resolver=resolver,
            cache_only=True,
            skip_cache_refresh=True,
        )
        root_name = str(analysis.get("root_playbook", {}).get("name") or playbook_id)
        seen: set[tuple[str, str]] = set()

        for script_row in analysis.get("scripts_used") or []:
            name = str(script_row.get("name") or "")
            script_id = str(script_row.get("script_id") or "")
            if not name and not script_id:
                continue
            key_tuple = ("scripts", script_id or name)
            if key_tuple in seen:
                continue
            seen.add(key_tuple)
            cached = find_script_in_index(profile, script_id=script_id) if script_id else None
            if not cached and name:
                cached = find_script_in_index(profile, name=name)
            resolved_id = str((cached or {}).get("id") or script_id or "")
            in_basket = f"scripts:{resolved_id}" in basket if resolved_id else False
            meta = cached or {"id": script_id, "name": name}
            copyable = bool(script_row.get("copyable")) and is_copyable_script(meta)
            origin = str(script_row.get("origin") or classify_script_entry(meta))
            if copyable:
                reason = None
            elif script_row.get("system"):
                reason = "system_script"
            elif script_row.get("pack_id") or script_row.get("pack_name"):
                reason = "content_pack_script"
            else:
                reason = f"{origin} script"
            dependencies.append({
                "playbook_id": playbook_id,
                "playbook_name": root_name,
                "kind": "script",
                "name": name or resolved_id,
                "id": resolved_id or None,
                "in_bundle": in_basket,
                "selectable": copyable,
                "origin": origin,
                "reason": reason,
            })

        for pb_row in analysis.get("playbooks_in_tree") or []:
            sub_id = str(pb_row.get("id") or "")
            if not sub_id or sub_id == playbook_id:
                continue
            if str(pb_row.get("role") or "") == "root":
                continue
            name = str(pb_row.get("name") or sub_id)
            key_tuple = ("playbooks", sub_id)
            if key_tuple in seen:
                continue
            seen.add(key_tuple)
            dependencies.append({
                "playbook_id": playbook_id,
                "playbook_name": root_name,
                "kind": "playbook",
                "name": name,
                "id": sub_id,
                "in_bundle": f"playbooks:{sub_id}" in basket,
                "selectable": True,
                "origin": "sub_playbook",
                "reason": None,
            })

    return {
        "source_profile": profile.slug,
        "playbook_ids": list(playbook_ids),
        "dependencies": dependencies,
    }
