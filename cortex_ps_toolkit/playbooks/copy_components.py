"""Copy a playbook with reachable sub-playbooks and referenced scripts."""

from __future__ import annotations

from typing import Any, Literal, Optional, Sequence

from ..cache.ensure import ensure_analysis_caches, ensure_playbooks_cache, ensure_scripts_cache
from ..credentials import CredentialProfile, get_profile
from ..ops_log import op_info
from ..platforms import assert_operation_supported
from ..scripts.copy import copy_scripts_to_tenant, plan_scripts_copy
from ..scripts.service import refresh_scripts_cache
from . import api
from .analysis import analyze_playbook
from .cache import find_playbook_in_index
from .copy import _classify_copy_action, resolve_playbook_meta
from .resolver import CachePlaybookResolver
from .playbook_remap import (
    log_playbook_remap_summary,
    register_playbook_remap_entry,
    seed_playbook_id_remap,
    target_playbook_id_after_save,
)
from .script_remap import build_script_id_remap
from .service import refresh_playbooks_cache
from .upload import save_playbook_document

CopyAction = Literal["copy", "update", "skip", "conflict"]


def _refresh_target_playbook_binding_maps(
    target: CredentialProfile,
    playbook_id_remap: dict[str, str],
    *,
    force: bool = False,
) -> tuple[dict[str, str], dict[str, str]]:
    """Rebuild target playbook name/id maps from cache (optionally force refresh first)."""
    if force:
        op_info("Refreshing playbooks cache on %s after playbook upload", target.slug)
        ensure_playbooks_cache(target, force=True)
    resolver = CachePlaybookResolver(target)
    name_to_id = dict(resolver.name_to_id())
    id_to_name = dict(resolver.id_to_name())
    for source_id, target_id in playbook_id_remap.items():
        target_name = id_to_name.get(str(target_id))
        if target_name:
            id_to_name[str(source_id)] = target_name
            name_to_id[target_name] = str(target_id)
    return name_to_id, id_to_name


def _playbook_copy_order(
    playbook_ids: Sequence[str],
    analysis: dict[str, Any],
    resolver: CachePlaybookResolver,
) -> list[str]:
    """Copy sub-playbooks before parents (deepest subs first), root last."""
    root_id = str(analysis["root_playbook"]["id"])
    id_to_name = {
        str(entry.get("id") or ""): str(entry.get("name") or "")
        for entry in analysis.get("playbooks_in_tree") or []
    }
    name_to_id = {name: pb_id for pb_id, name in id_to_name.items() if name}
    child_map: dict[str, set[str]] = {pb_id: set() for pb_id in id_to_name}

    for pb_id in id_to_name:
        try:
            playbook = resolver.load(pb_id)
        except Exception:
            continue
        for node in (playbook.get("tasks") or {}).values():
            if node.get("type") != "playbook":
                continue
            inner = node.get("task") or {}
            child_id = inner.get("playbookId") or inner.get("playbookid")
            child_name = inner.get("playbookName") or inner.get("playbookname")
            child_key = None
            if child_id and str(child_id) in id_to_name:
                child_key = str(child_id)
            elif child_name and child_name in name_to_id:
                child_key = name_to_id[child_name]
            if child_key:
                child_map.setdefault(pb_id, set()).add(child_key)

    depth: dict[str, int] = {}

    def depth_for(pb_id: str, stack: set[str]) -> int:
        if pb_id in depth:
            return depth[pb_id]
        if pb_id in stack:
            return 0
        stack.add(pb_id)
        child_depths = [depth_for(child, stack) + 1 for child in child_map.get(pb_id, set())]
        depth[pb_id] = max(child_depths) if child_depths else 0
        return depth[pb_id]

    unique_ids = list(dict.fromkeys(playbook_ids))
    return sorted(unique_ids, key=lambda pb_id: (depth_for(pb_id, set()), pb_id == root_id, pb_id))


def plan_playbook_components_copy(
    source_profile: str,
    target_profile: str,
    playbook_id: str,
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
) -> dict[str, Any]:
    source = get_profile(source_profile)
    target = get_profile(target_profile)
    assert_operation_supported("playbooks.copy", source.tenant_type)
    assert_operation_supported("playbooks.copy", target.tenant_type)
    assert_operation_supported("scripts.copy", source.tenant_type)
    assert_operation_supported("scripts.copy", target.tenant_type)

    op_info(
        "Planning playbook component copy %s → %s (playbook=%s)",
        source.slug,
        target.slug,
        playbook_id,
    )
    ensure_analysis_caches(source)
    ensure_playbooks_cache(target)
    ensure_scripts_cache(target)
    resolver = CachePlaybookResolver(source)
    analysis = analyze_playbook(source.slug, playbook_id, resolver=resolver)
    scope = analysis["copy_scope"]
    playbook_ids = scope["playbook_ids"]
    script_ids = scope["script_ids"]

    script_plan = (
        plan_scripts_copy(
            source.slug,
            target.slug,
            script_ids,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
        )
        if script_ids
        else {
            "items": [],
            "counts": {"total": 0, "copy": 0, "update": 0, "skip": 0, "conflict": 0},
            "would_abort": False,
            "conflicts": [],
        }
    )

    playbook_items: list[dict[str, Any]] = []
    playbook_conflicts: list[dict[str, Any]] = []
    for pb_id in _playbook_copy_order(playbook_ids, analysis, resolver):
        entry = resolve_playbook_meta(source, pb_id)
        name = str(entry.get("name") or pb_id)
        existing = find_playbook_in_index(target, name=name)
        action = _classify_copy_action(
            existing=existing,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
        )
        item = {
            "playbook_id": pb_id,
            "name": name,
            "action": action,
            "role": next(
                (row.get("role") for row in analysis["playbooks_in_tree"] if str(row.get("id")) == pb_id),
                "sub_playbook",
            ),
        }
        if existing:
            item["target_id"] = existing.get("id")
        playbook_items.append(item)
        if action == "conflict":
            playbook_conflicts.append(item)

    playbook_counts = {
        "total": len(playbook_items),
        "copy": sum(1 for item in playbook_items if item["action"] == "copy"),
        "update": sum(1 for item in playbook_items if item["action"] == "update"),
        "skip": sum(1 for item in playbook_items if item["action"] == "skip"),
        "conflict": len(playbook_conflicts),
    }

    would_abort = stop_on_conflict and (
        script_plan.get("would_abort") or bool(playbook_conflicts)
    )

    return {
        "source_profile": source.slug,
        "target_profile": target.slug,
        "root_playbook_id": playbook_id,
        "root_playbook_name": analysis["root_playbook"]["name"],
        "overwrite": overwrite,
        "stop_on_conflict": stop_on_conflict,
        "analysis_summary": scope,
        "warnings": analysis.get("warnings") or [],
        "missing_sub_playbooks": analysis.get("missing_sub_playbooks") or [],
        "unresolved_scripts": analysis.get("unresolved_scripts") or [],
        "scripts": script_plan,
        "playbooks": {
            "items": playbook_items,
            "counts": playbook_counts,
            "conflicts": playbook_conflicts,
            "copy_order": _playbook_copy_order(playbook_ids, analysis, resolver),
        },
        "integration_commands_used": analysis.get("integration_commands_used") or [],
        "would_abort": would_abort,
    }


def copy_playbook_components_to_tenant(
    source_profile: str,
    target_profile: str,
    playbook_id: str,
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
) -> dict[str, Any]:
    source = get_profile(source_profile)
    target = get_profile(target_profile)
    plan = plan_playbook_components_copy(
        source_profile,
        target_profile,
        playbook_id,
        overwrite=overwrite,
        stop_on_conflict=stop_on_conflict,
    )

    if plan["would_abort"]:
        conflicts = plan["scripts"].get("conflicts") or plan["playbooks"]["conflicts"]
        conflict_names = ", ".join(
            item.get("name") or item.get("script_id") or item.get("playbook_id") or "?"
            for item in conflicts
        )
        op_info("Component copy aborted: name conflict(s): %s", conflict_names)
        return {
            "source_profile": source.slug,
            "target_profile": target.slug,
            "aborted": True,
            "reason": f"Stopped due to name conflict(s): {conflict_names}",
            "plan": plan,
            "script_results": [],
            "playbook_results": [],
        }

    if plan["missing_sub_playbooks"]:
        missing = ", ".join(item["lookup_key"] for item in plan["missing_sub_playbooks"])
        op_info("Component copy aborted: missing sub-playbook(s): %s", missing)
        return {
            "source_profile": source.slug,
            "target_profile": target.slug,
            "aborted": True,
            "reason": f"Cannot copy: unresolved sub-playbook reference(s): {missing}",
            "plan": plan,
            "script_results": [],
            "playbook_results": [],
        }

    script_results: list[dict[str, Any]] = []
    script_ids = plan["analysis_summary"]["script_ids"]
    if script_ids:
        op_info(
            "Copying %d automation script(s) before playbooks (%s → %s)",
            len(script_ids),
            source.slug,
            target.slug,
        )
        script_copy = copy_scripts_to_tenant(
            source.slug,
            target.slug,
            script_ids,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
        )
        if script_copy.get("aborted"):
            op_info("Component copy aborted during script copy: %s", script_copy.get("reason"))
            return {
                "source_profile": source.slug,
                "target_profile": target.slug,
                "aborted": True,
                "reason": script_copy.get("reason") or "Script copy aborted",
                "plan": plan,
                "script_results": script_copy.get("results") or [],
                "playbook_results": [],
            }
        script_results = script_copy.get("results") or []

    op_info("Refreshing scripts cache on %s before playbook binding", target.slug)
    ensure_scripts_cache(target, force=True)
    script_id_remap = build_script_id_remap(
        plan["scripts"].get("items") or [],
        script_results,
        target,
    )

    op_info("Refreshing playbooks cache on %s before sub-playbook binding", target.slug)
    playbook_id_remap = seed_playbook_id_remap(plan["playbooks"]["items"])
    log_playbook_remap_summary(playbook_id_remap, target)
    playbook_name_to_id, playbook_id_to_name = _refresh_target_playbook_binding_maps(
        target,
        playbook_id_remap,
        force=True,
    )

    playbook_results: list[dict[str, Any]] = []
    binding_issues: list[dict[str, Any]] = []

    for pb_id in plan["playbooks"]["copy_order"]:
        item = next(row for row in plan["playbooks"]["items"] if row["playbook_id"] == pb_id)
        name = item["name"]
        action = item.get("action")
        if action == "skip":
            op_info("Skipping playbook %r on %s (already exists)", name, target.slug)
            target_id = str(item.get("target_id") or "")
            if not target_id:
                existing = find_playbook_in_index(target, name=name)
                target_id = str(existing.get("id") or "") if existing else ""
            if target_id:
                playbook_name_to_id[name] = target_id
                playbook_id_to_name[target_id] = name
                register_playbook_remap_entry(
                    playbook_id_remap,
                    source_id=pb_id,
                    target_id=target_id,
                    name=name,
                    target=target,
                )
            playbook_results.append({
                "playbook_id": pb_id,
                "name": name,
                "status": "skipped",
                "target_playbook_id": target_id or None,
                "reason": f"Playbook {name!r} already exists on {target.slug}",
            })
            continue
        if action == "conflict":
            playbook_results.append({
                "playbook_id": pb_id,
                "name": name,
                "status": "conflict",
                "reason": f"Playbook {name!r} already exists on {target.slug}",
            })
            continue

        overwrite_save = action == "update"
        target_playbook_id = str(item.get("target_id") or "") if overwrite_save else None

        op_info(
            "Saving playbook %r (%s) to %s [%s]",
            name,
            pb_id,
            target.slug,
            "overwrite" if overwrite_save else "create",
        )
        playbook_doc = api.get_playbook(source, pb_id)
        filename = f"{name.replace('/', '_')}.yml"
        saved, status_code, unresolved = save_playbook_document(
            target,
            playbook_doc,
            filename=filename,
            target_playbook_id=target_playbook_id or None,
            overwrite=overwrite_save,
            source_profile=source,
            playbook_name_to_id=playbook_name_to_id,
            playbook_id_to_name=playbook_id_to_name,
            script_id_remap=script_id_remap,
            playbook_id_remap=playbook_id_remap,
        )
        if unresolved:
            binding_issues.extend([{**issue, "playbook_id": pb_id, "playbook_name": name} for issue in unresolved])
            op_info(
                "Playbook %r: %d unresolved binding(s)",
                name,
                len(unresolved),
            )
        saved_id = target_playbook_id_after_save(
            target,
            name=name,
            saved=saved,
            fallback_id=target_playbook_id,
        )
        saved_name = str(saved.get("name") or name)
        if saved_id:
            playbook_name_to_id[saved_name] = saved_id
            playbook_id_to_name[saved_id] = saved_name
            register_playbook_remap_entry(
                playbook_id_remap,
                source_id=pb_id,
                target_id=saved_id,
                name=saved_name,
                target=target,
            )

        playbook_results.append({
            "playbook_id": pb_id,
            "name": name,
            "status": "updated" if overwrite_save else "copied",
            "target_playbook_id": target_playbook_id or saved_id or None,
            "response": saved,
            "status_code": status_code,
            "binding_unresolved": unresolved,
        })
        playbook_name_to_id, playbook_id_to_name = _refresh_target_playbook_binding_maps(
            target,
            playbook_id_remap,
            force=True,
        )

    op_info("Refreshing playbooks cache on %s after component copy", target.slug)
    refresh_playbooks_cache(target)

    failed_scripts = [r for r in script_results if r.get("status") == "failed"]
    if binding_issues or failed_scripts:
        op_info(
            "Component copy finished with issues: %d script failure(s), %d binding issue(s)",
            len(failed_scripts),
            len(binding_issues),
        )
    else:
        op_info(
            "Component copy finished: %d script(s), %d playbook(s)",
            len(script_results),
            len([r for r in playbook_results if r.get("status") in ("copied", "updated")]),
        )

    return {
        "source_profile": source.slug,
        "target_profile": target.slug,
        "root_playbook_id": playbook_id,
        "root_playbook_name": plan["root_playbook_name"],
        "script_results": script_results,
        "playbook_results": playbook_results,
        "binding_issues": binding_issues,
        "script_id_remap": script_id_remap,
        "playbook_id_remap": playbook_id_remap,
        "warnings": plan.get("warnings") or [],
    }
