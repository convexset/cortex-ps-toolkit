"""Copy a playbook with reachable sub-playbooks and referenced scripts."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Literal, Mapping, Optional, Sequence

from ..content.copy_modes import classify_copy_action
from ..content.copy_plan_params import effective_upload_name, normalize_copy_kwargs
from ..content.operation_plan import wrap_copy_plan

from ..cache.ensure import check_analysis_caches, ensure_analysis_caches, ensure_playbooks_cache, ensure_scripts_cache
from ..content.post_copy_diff import (
    aggregate_copy_diff_report,
    apply_deep_copy_post_diffs,
    new_copy_run_telemetry,
)
from ..core.client import TenantApiError
from ..core.staged_progress import StagedProgressReporter
from ..credentials import CredentialProfile, get_profile
from ..ops_log import op_action, op_info, op_warn
from ..server_config import (
    copy_binding_cache_pause_seconds,
    copy_binding_resolve_retries,
    copy_binding_retry_pause_seconds,
)
from ..platforms import assert_operation_supported
from ..scripts.copy import plan_scripts_copy
from ..scripts import api as scripts_api
from ..scripts.upload import save_script_document
from ..scripts.copy_helpers import target_script_id_after_save
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
from .yaml_helpers import iter_sub_playbook_refs

CopyAction = Literal["copy", "update", "skip", "conflict"]

_UPLOAD_WORKERS = 5
ProgressCallback = Callable[[dict[str, Any]], None]


def _source_names_from_items(items_by_id: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {
        str(pb_id): str(item.get("name") or pb_id)
        for pb_id, item in items_by_id.items()
        if pb_id
    }


def _merge_remap_into_binding_maps(
    name_to_id: dict[str, str],
    id_to_name: dict[str, str],
    playbook_id_remap: dict[str, str],
    source_names: dict[str, str],
) -> None:
    for source_id, target_id in playbook_id_remap.items():
        tid = str(target_id)
        tname = id_to_name.get(tid) or source_names.get(str(source_id), "")
        if not tname:
            continue
        name_to_id[tname] = tid
        id_to_name[tid] = tname
        id_to_name[str(source_id)] = tname


def _resolve_sub_ref_ready(
    *,
    source_id: Optional[str],
    playbook_name: Optional[str],
    pending_source_ids: set[str],
    playbook_name_to_id: dict[str, str],
    playbook_id_remap: dict[str, str],
    playbook_id_to_name: dict[str, str],
    source_names: dict[str, str],
) -> bool:
    if source_id and source_id in pending_source_ids:
        return False
    names_to_try: list[str] = []
    if playbook_name:
        names_to_try.append(str(playbook_name))
    if source_id:
        if source_id in playbook_id_to_name:
            names_to_try.append(str(playbook_id_to_name[source_id]))
        if source_id in source_names:
            names_to_try.append(str(source_names[source_id]))
    for name in names_to_try:
        if name in playbook_name_to_id:
            return True
    if source_id and source_id in playbook_id_remap:
        return True
    return not source_id and not playbook_name


def _unresolved_sub_ref_details(
    playbook_doc: dict[str, Any],
    *,
    pending_source_ids: set[str],
    playbook_name_to_id: dict[str, str],
    playbook_id_remap: dict[str, str],
    playbook_id_to_name: Optional[dict[str, str]] = None,
    source_names: Optional[dict[str, str]] = None,
) -> list[str]:
    playbook_id_to_name = playbook_id_to_name or {}
    source_names = source_names or {}
    details: list[str] = []
    for task_id, playbook_id, playbook_name, label in iter_sub_playbook_refs(playbook_doc):
        source_id = str(playbook_id) if playbook_id else None
        if source_id and source_id in pending_source_ids:
            details.append(
                f"task {task_id} ({label}): sub-playbook {source_id!r} not uploaded yet",
            )
            continue
        if _resolve_sub_ref_ready(
            source_id=source_id,
            playbook_name=str(playbook_name) if playbook_name else None,
            pending_source_ids=pending_source_ids,
            playbook_name_to_id=playbook_name_to_id,
            playbook_id_remap=playbook_id_remap,
            playbook_id_to_name=playbook_id_to_name,
            source_names=source_names,
        ):
            continue
        ref = playbook_name or source_id or "?"
        hint = ""
        if source_id and source_id in source_names:
            expected = source_names[source_id]
            target_id = playbook_name_to_id.get(expected)
            if target_id:
                hint = f" (target id {target_id!r} by name {expected!r})"
            else:
                hint = f" (expected name {expected!r} not in binding index)"
        details.append(f"task {task_id} ({label}): unresolved sub-playbook ref {ref!r}{hint}")
    return details


def _build_copy_stage_labels(plan: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    if plan.get("analysis_summary", {}).get("script_ids"):
        labels.append("Parallel Script Copy")
        labels.append("Pause + Script Cache Refresh")
    labels.append("Initial Playbook Binding Cache Refresh")
    waves = plan.get("execution_plan", {}).get("playbook_waves") or []
    for index, wave in enumerate(waves, start=1):
        if not wave:
            continue
        labels.append(f"Parallel Playbook Upload (Wave {index})")
        labels.append(f"Pause + Playbook Cache Refresh (Wave {index})")
    labels.append("Final Playbook Cache Refresh")
    return labels


def _refresh_target_playbook_binding_maps(
    target: CredentialProfile,
    playbook_id_remap: dict[str, str],
    *,
    force: bool = False,
    source_names: Optional[dict[str, str]] = None,
    pause_seconds: Optional[float] = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Rebuild target playbook name/id maps from cache (optionally force refresh first)."""
    source_names = source_names or {}
    if force:
        pause = copy_binding_cache_pause_seconds() if pause_seconds is None else max(0.0, pause_seconds)
        if pause > 0:
            op_info(
                "Waiting %.1fs before refreshing playbooks cache on %s (tenant index propagation)",
                pause,
                target.slug,
            )
            time.sleep(pause)
        ensure_playbooks_cache(target, force=True)
    resolver = CachePlaybookResolver(target)
    name_to_id = dict(resolver.name_to_id())
    id_to_name = dict(resolver.id_to_name())
    _merge_remap_into_binding_maps(name_to_id, id_to_name, playbook_id_remap, source_names)
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


def _sub_playbook_refs_ready(
    playbook_doc: dict[str, Any],
    *,
    pending_source_ids: set[str],
    playbook_name_to_id: dict[str, str],
    playbook_id_remap: dict[str, str],
    playbook_id_to_name: Optional[dict[str, str]] = None,
    source_names: Optional[dict[str, str]] = None,
) -> bool:
    playbook_id_to_name = playbook_id_to_name or {}
    source_names = source_names or {}
    for _task_id, playbook_id, playbook_name, _label in iter_sub_playbook_refs(playbook_doc):
        source_id = str(playbook_id) if playbook_id else None
        if not _resolve_sub_ref_ready(
            source_id=source_id,
            playbook_name=str(playbook_name) if playbook_name else None,
            pending_source_ids=pending_source_ids,
            playbook_name_to_id=playbook_name_to_id,
            playbook_id_remap=playbook_id_remap,
            playbook_id_to_name=playbook_id_to_name,
            source_names=source_names,
        ):
            return False
    return True


def _plan_playbook_upload_waves(
    resolver: CachePlaybookResolver,
    target: CredentialProfile,
    copy_order: Sequence[str],
    items_by_id: dict[str, dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Predict parallel upload waves (matches copy_playbook_components_to_tenant)."""
    playbook_name_to_id: dict[str, str] = {}
    playbook_id_remap: dict[str, str] = {}

    for pb_id in copy_order:
        item = items_by_id.get(pb_id)
        if not item or item.get("action") != "skip":
            continue
        name = str(item.get("name") or pb_id)
        target_id = str(item.get("target_id") or "")
        if not target_id:
            existing = find_playbook_in_index(target, name=name)
            target_id = str(existing.get("id") or "") if existing else ""
        if target_id:
            playbook_name_to_id[name] = target_id
            playbook_id_remap[pb_id] = target_id

    pending = [
        pb_id
        for pb_id in copy_order
        if items_by_id.get(pb_id, {}).get("action") in ("copy", "update")
    ]
    if not pending:
        return []

    docs = {pb_id: resolver.load(pb_id) for pb_id in pending}
    waves: list[list[dict[str, Any]]] = []

    while pending:
        ready = [
            pb_id
            for pb_id in pending
            if _sub_playbook_refs_ready(
                docs[pb_id],
                pending_source_ids=set(pending),
                playbook_name_to_id=playbook_name_to_id,
                playbook_id_remap=playbook_id_remap,
            )
        ]
        if not ready:
            waves.append(
                [
                    {
                        "playbook_id": pb_id,
                        "name": str(items_by_id[pb_id].get("name") or pb_id),
                        "action": items_by_id[pb_id].get("action"),
                        "role": items_by_id[pb_id].get("role"),
                        "blocked": True,
                    }
                    for pb_id in pending
                ]
            )
            break
        wave_rows = [
            {
                "playbook_id": pb_id,
                "name": str(items_by_id[pb_id].get("name") or pb_id),
                "action": items_by_id[pb_id].get("action"),
                "role": items_by_id[pb_id].get("role"),
            }
            for pb_id in ready
        ]
        waves.append(wave_rows)
        for pb_id in ready:
            item = items_by_id[pb_id]
            name = str(item.get("name") or pb_id)
            target_id = str(item.get("target_id") or f"planned:{pb_id}")
            playbook_name_to_id[name] = target_id
            playbook_id_remap[pb_id] = target_id
        pending = [pb_id for pb_id in pending if pb_id not in ready]

    return waves


def _upload_script_item(
    source: CredentialProfile,
    target: CredentialProfile,
    script_id: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    name = str(item.get("name") or script_id)
    action = item.get("action")
    if action == "blocked_non_copyable":
        return {
            "script_id": script_id,
            "name": name,
            "status": "blocked",
            "reason": item.get("reason") or f"Script {name!r} is not copyable",
        }
    if action == "skip":
        skipped_target_id = str(item.get("target_id") or "")
        return {
            "script_id": script_id,
            "name": name,
            "status": "skipped",
            "target_script_id": skipped_target_id or None,
            "reason": f"Script {name!r} already exists on {target.slug}",
        }
    if action == "conflict":
        return {
            "script_id": script_id,
            "name": name,
            "status": "conflict",
            "reason": f"Script {name!r} already exists on {target.slug}",
        }

    overwrite_save = action == "update"
    target_script_id = str(item.get("target_id") or "") if overwrite_save else None
    script_doc = scripts_api.get_script(source, script_id)
    filename = f"{name.replace('/', '_')}.yml"
    try:
        op_info(
            "Copying script %r (%s) %s → %s [%s]",
            name,
            script_id,
            source.slug,
            target.slug,
            "overwrite" if overwrite_save else "create",
        )
        saved, status_code = save_script_document(
            target,
            script_doc,
            filename=filename,
            target_script_id=target_script_id or None,
            overwrite=overwrite_save,
        )
    except TenantApiError as exc:
        return {
            "script_id": script_id,
            "name": name,
            "status": "failed",
            "target_script_id": target_script_id or None,
            "error": str(exc),
            "response": exc.body if isinstance(exc.body, dict) else {},
            "status_code": exc.status_code,
        }
    resolved_target_id = target_script_id_after_save(
        target,
        name=name,
        saved=saved,
        fallback_id=target_script_id,
    )
    return {
        "script_id": script_id,
        "name": name,
        "status": "updated" if overwrite_save else "copied",
        "target_script_id": resolved_target_id or None,
        "response": saved,
        "status_code": status_code,
    }


def _copy_scripts_parallel(
    source: CredentialProfile,
    target: CredentialProfile,
    script_ids: Sequence[str],
    plan_items: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    plan_by_id = {item["script_id"]: item for item in plan_items}
    results: list[dict[str, Any]] = []
    upload_ids: list[str] = []
    for script_id in script_ids:
        item = plan_by_id[script_id]
        if item.get("action") in ("copy", "update"):
            upload_ids.append(script_id)
        else:
            results.append(_upload_script_item(source, target, script_id, item))

    if not upload_ids:
        return results

    with ThreadPoolExecutor(max_workers=_UPLOAD_WORKERS) as pool:
        futures = {
            pool.submit(_upload_script_item, source, target, script_id, plan_by_id[script_id]): script_id
            for script_id in upload_ids
        }
        for future in as_completed(futures):
            results.append(future.result())
    return results


def _upload_playbook_item(
    source: CredentialProfile,
    target: CredentialProfile,
    pb_id: str,
    item: dict[str, Any],
    *,
    playbook_name_to_id: dict[str, str],
    playbook_id_to_name: dict[str, str],
    script_id_remap: dict[str, str],
    playbook_id_remap: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]], Optional[dict[str, str]]]:
    name = str(item.get("name") or pb_id)
    action = item.get("action")
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
        op_info("Playbook %r: %d unresolved binding(s)", name, len(unresolved))
    saved_id = target_playbook_id_after_save(
        target,
        name=name,
        saved=saved,
        fallback_id=target_playbook_id,
    )
    saved_name = str(saved.get("name") or name)
    remap_update = (
        {"source_id": pb_id, "target_id": saved_id, "name": saved_name}
        if saved_id
        else None
    )
    result = {
        "playbook_id": pb_id,
        "name": name,
        "status": "updated" if overwrite_save else "copied",
        "target_playbook_id": target_playbook_id or saved_id or None,
        "response": saved,
        "status_code": status_code,
        "binding_unresolved": unresolved,
    }
    binding_issues = [{**issue, "playbook_id": pb_id, "playbook_name": name} for issue in unresolved]
    return result, binding_issues, remap_update


def _apply_playbook_remap_updates(
    target: CredentialProfile,
    playbook_id_remap: dict[str, str],
    playbook_name_to_id: dict[str, str],
    playbook_id_to_name: dict[str, str],
    updates: Sequence[Optional[dict[str, str]]],
) -> None:
    for update in updates:
        if not update:
            continue
        saved_id = str(update.get("target_id") or "")
        saved_name = str(update.get("name") or "")
        source_id = str(update.get("source_id") or "")
        if not saved_id or not saved_name or not source_id:
            continue
        playbook_name_to_id[saved_name] = saved_id
        playbook_id_to_name[saved_id] = saved_name
        register_playbook_remap_entry(
            playbook_id_remap,
            source_id=source_id,
            target_id=saved_id,
            name=saved_name,
            target=target,
        )


def plan_playbook_components_copy(
    source_profile: str,
    target_profile: str,
    playbook_id: str,
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    copy_mode: Optional[str] = None,
    rename_suffix: str = "",
    rename_map: Optional[Mapping[str, str]] = None,
    cache_only: bool = True,
    skip_cache_refresh: bool = True,
) -> dict[str, Any]:
    opts = normalize_copy_kwargs(
        overwrite=overwrite,
        stop_on_conflict=stop_on_conflict,
        copy_mode=copy_mode,
        rename_suffix=rename_suffix,
        rename_map=rename_map,
    )
    mode = opts["copy_mode"]
    overwrite = opts["overwrite"]
    stop_on_conflict = opts["stop_on_conflict"]
    rename_suffix = opts["rename_suffix"]
    rename_map = opts["rename_map"]
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
    if skip_cache_refresh or cache_only:
        check_analysis_caches(source)
    else:
        ensure_analysis_caches(source)
    if not skip_cache_refresh:
        ensure_playbooks_cache(target)
        ensure_scripts_cache(target)
    resolver = CachePlaybookResolver(source, allow_live_fetch=True)
    analysis = analyze_playbook(
        source.slug,
        playbook_id,
        resolver=resolver,
        cache_only=cache_only,
        skip_cache_refresh=skip_cache_refresh,
    )
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
            copy_mode=mode,
            rename_suffix=rename_suffix,
            rename_map=rename_map,
            cache_only=cache_only,
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
        action, extra = classify_copy_action(
            existing=existing,
            mode=mode,
            source_name=name,
            rename_suffix=rename_suffix,
            rename_map=rename_map,
            item_key=pb_id,
            name_exists=lambda n: find_playbook_in_index(target, name=n),
            stop_on_conflict=stop_on_conflict,
        )
        item = {
            "playbook_id": pb_id,
            "name": name,
            "action": action,
            **extra,
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

    would_abort = (stop_on_conflict and (
        script_plan.get("would_abort") or bool(playbook_conflicts)
    )) or (mode == "copy_as_new" and (
        script_plan.get("would_abort") or bool(playbook_conflicts)
    ))

    copy_order = _playbook_copy_order(playbook_ids, analysis, resolver)
    items_by_id = {item["playbook_id"]: item for item in playbook_items}
    playbook_waves = _plan_playbook_upload_waves(resolver, target, copy_order, items_by_id)

    flat_items: list[dict[str, Any]] = []
    for row in script_plan.get("items") or []:
        flat_items.append({**row, "kind": "script"})
    for row in playbook_items:
        flat_items.append({**row, "kind": "playbook"})

    legacy = {
        "source_profile": source.slug,
        "target_profile": target.slug,
        "root_playbook_id": playbook_id,
        "root_playbook_name": analysis["root_playbook"]["name"],
        "overwrite": overwrite,
        "stop_on_conflict": stop_on_conflict,
        "copy_mode": mode,
        "rename_suffix": rename_suffix,
        "items": flat_items,
        "conflicts": (script_plan.get("conflicts") or []) + playbook_conflicts,
        "analysis_summary": scope,
        "warnings": analysis.get("warnings") or [],
        "missing_sub_playbooks": analysis.get("missing_sub_playbooks") or [],
        "unresolved_scripts": analysis.get("unresolved_scripts") or [],
        "scripts": script_plan,
        "playbooks": {
            "items": playbook_items,
            "counts": playbook_counts,
            "conflicts": playbook_conflicts,
            "copy_order": copy_order,
        },
        "integration_commands_used": analysis.get("integration_commands_used") or [],
        "execution_plan": {
            "script_phase": {
                "parallel": True,
                "items": script_plan.get("items") or [],
                "cache_refresh_after": {"profile": target.slug, "scope": "scripts"},
            },
            "playbook_waves": playbook_waves,
            "playbook_skipped": [
                {
                    "playbook_id": item["playbook_id"],
                    "name": item["name"],
                    "action": item["action"],
                    "role": item.get("role"),
                    "target_id": item.get("target_id"),
                }
                for item in playbook_items
                if item.get("action") == "skip"
            ],
            "playbook_cache_refresh_after_each_wave": bool(playbook_waves),
            "final_playbook_cache_refresh": {"profile": target.slug, "scope": "playbooks"},
        },
        "would_abort": would_abort,
        "counts": {
            "total": len(flat_items),
            "copy": sum(1 for i in flat_items if i.get("action") in ("copy", "copy_as_new")),
            "update": sum(1 for i in flat_items if i.get("action") == "update"),
            "skip": sum(1 for i in flat_items if i.get("action") == "skip"),
            "conflict": sum(1 for i in flat_items if i.get("action") == "conflict"),
        },
    }
    return wrap_copy_plan(
        legacy,
        operation="playbooks.copy_components",
        mode=mode,
        rename_suffix=rename_suffix,
        extra_steps=[
            {"label": "Parallel script upload phase", "automated": True},
            {"label": "Playbook upload waves with binding remap", "automated": True},
        ],
    )


def copy_playbook_components_to_tenant(
    source_profile: str,
    target_profile: str,
    playbook_id: str,
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    copy_mode: Optional[str] = None,
    rename_suffix: str = "",
    rename_map: Optional[Mapping[str, str]] = None,
    post_copy_diff: bool = False,
    on_progress: Optional[ProgressCallback] = None,
) -> dict[str, Any]:
    source = get_profile(source_profile)
    target = get_profile(target_profile)
    plan = plan_playbook_components_copy(
        source_profile,
        target_profile,
        playbook_id,
        overwrite=overwrite,
        stop_on_conflict=stop_on_conflict,
        copy_mode=copy_mode,
        rename_suffix=rename_suffix,
        rename_map=rename_map,
    )
    items_by_id = {row["playbook_id"]: row for row in plan["playbooks"]["items"]}
    source_names = _source_names_from_items(items_by_id)
    progress = StagedProgressReporter(
        _build_copy_stage_labels(plan),
        title="Playbook Copy Progress",
        on_progress=on_progress,
        operation="playbooks.copy_components",
    )

    with op_action(
        "Deep playbook component copy %s → %s (root=%s)",
        source.slug,
        target.slug,
        plan.get("root_playbook_name") or playbook_id,
    ):
        return _execute_playbook_components_copy(
            source,
            target,
            playbook_id,
            plan,
            items_by_id=items_by_id,
            source_names=source_names,
            progress=progress,
            post_copy_diff=post_copy_diff,
        )


def _execute_playbook_components_copy(
    source: CredentialProfile,
    target: CredentialProfile,
    playbook_id: str,
    plan: dict[str, Any],
    *,
    items_by_id: dict[str, dict[str, Any]],
    source_names: dict[str, str],
    progress: StagedProgressReporter,
    post_copy_diff: bool = False,
) -> dict[str, Any]:
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
            "Copying %d automation script(s) in parallel before playbooks (%s → %s)",
            len(script_ids),
            source.slug,
            target.slug,
        )
        script_results = _copy_scripts_parallel(
            source,
            target,
            script_ids,
            plan["scripts"].get("items") or [],
        )
        progress.complete_stage("Parallel Script Copy")
        failed_scripts = [row for row in script_results if row.get("status") == "failed"]
        if failed_scripts:
            op_info("Component copy aborted during script copy: %d failure(s)", len(failed_scripts))
            return {
                "source_profile": source.slug,
                "target_profile": target.slug,
                "aborted": True,
                "reason": f"Script copy failed: {failed_scripts[0].get('error') or failed_scripts[0].get('name')}",
                "plan": plan,
                "script_results": script_results,
                "playbook_results": [],
            }

    if plan["analysis_summary"]["script_ids"]:
        op_info("Refreshing scripts cache on %s before playbook binding", target.slug)
        ensure_scripts_cache(target, force=True)
        progress.complete_stage("Pause + Script Cache Refresh")
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
        source_names=source_names,
    )
    progress.complete_stage("Initial Playbook Binding Cache Refresh")

    playbook_results: list[dict[str, Any]] = []
    binding_issues: list[dict[str, Any]] = []
    pending_upload: list[str] = []
    wave_index = 0

    for pb_id in plan["playbooks"]["copy_order"]:
        item = items_by_id[pb_id]
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
        pending_upload.append(pb_id)

    playbook_source_docs: dict[str, dict[str, Any]] = {
        pb_id: api.get_playbook(source, pb_id) for pb_id in pending_upload
    }
    playbook_docs = playbook_source_docs

    max_upload_waves = max(len(pending_upload) * 3, 1) + copy_binding_resolve_retries()
    while pending_upload:
        if wave_index >= max_upload_waves:
            op_warn(
                "Component copy exceeded %d playbook upload wave(s); stopping with %d pending",
                max_upload_waves,
                len(pending_upload),
                persistent=True,
            )
            break
        ready = [
            pb_id
            for pb_id in pending_upload
            if _sub_playbook_refs_ready(
                playbook_docs[pb_id],
                pending_source_ids=set(pending_upload),
                playbook_name_to_id=playbook_name_to_id,
                playbook_id_remap=playbook_id_remap,
                playbook_id_to_name=playbook_id_to_name,
                source_names=source_names,
            )
        ]
        if not ready:
            retries = copy_binding_resolve_retries()
            for attempt in range(retries):
                pause = copy_binding_retry_pause_seconds(attempt)
                op_info(
                    "Sub-playbook bindings not ready on %s; retry %d/%d after %.0fs pause + cache refresh",
                    target.slug,
                    attempt + 1,
                    retries,
                    pause,
                )
                playbook_name_to_id, playbook_id_to_name = _refresh_target_playbook_binding_maps(
                    target,
                    playbook_id_remap,
                    force=True,
                    source_names=source_names,
                    pause_seconds=pause,
                )
                ready = [
                    pb_id
                    for pb_id in pending_upload
                    if _sub_playbook_refs_ready(
                        playbook_docs[pb_id],
                        pending_source_ids=set(pending_upload),
                        playbook_name_to_id=playbook_name_to_id,
                        playbook_id_remap=playbook_id_remap,
                        playbook_id_to_name=playbook_id_to_name,
                        source_names=source_names,
                    )
                ]
                if ready:
                    break

        if not ready:
            stuck = ", ".join(items_by_id[pb_id]["name"] for pb_id in pending_upload)
            detail_lines: list[str] = []
            for pb_id in pending_upload:
                detail_lines.extend(
                    _unresolved_sub_ref_details(
                        playbook_docs[pb_id],
                        pending_source_ids=set(pending_upload),
                        playbook_name_to_id=playbook_name_to_id,
                        playbook_id_remap=playbook_id_remap,
                        playbook_id_to_name=playbook_id_to_name,
                        source_names=source_names,
                    )
                )
            op_warn(
                "Component copy stalled: unresolved sub-playbook binding(s) for %s",
                stuck,
                persistent=True,
            )
            for line in detail_lines[:20]:
                op_warn("  %s", line, persistent=True)
            for pb_id in pending_upload:
                playbook_results.append({
                    "playbook_id": pb_id,
                    "name": items_by_id[pb_id]["name"],
                    "status": "failed",
                    "reason": "Unresolved sub-playbook reference(s) after prior uploads",
                    "binding_details": _unresolved_sub_ref_details(
                        playbook_docs[pb_id],
                        pending_source_ids=set(pending_upload),
                        playbook_name_to_id=playbook_name_to_id,
                        playbook_id_remap=playbook_id_remap,
                        playbook_id_to_name=playbook_id_to_name,
                        source_names=source_names,
                    ),
                })
            break

        wave_index += 1
        wave_results: list[dict[str, Any]] = []
        wave_binding_issues: list[dict[str, Any]] = []
        wave_remap_updates: list[Optional[dict[str, str]]] = []
        with ThreadPoolExecutor(max_workers=_UPLOAD_WORKERS) as pool:
            futures = {
                pool.submit(
                    _upload_playbook_item,
                    source,
                    target,
                    pb_id,
                    items_by_id[pb_id],
                    playbook_name_to_id=dict(playbook_name_to_id),
                    playbook_id_to_name=dict(playbook_id_to_name),
                    script_id_remap=script_id_remap,
                    playbook_id_remap=playbook_id_remap,
                ): pb_id
                for pb_id in ready
            }
            for future in as_completed(futures):
                result, issues, remap_update = future.result()
                wave_results.append(result)
                wave_binding_issues.extend(issues)
                wave_remap_updates.append(remap_update)

        _apply_playbook_remap_updates(
            target,
            playbook_id_remap,
            playbook_name_to_id,
            playbook_id_to_name,
            wave_remap_updates,
        )
        playbook_results.extend(wave_results)
        binding_issues.extend(wave_binding_issues)
        progress.complete_stage(f"Parallel Playbook Upload (Wave {wave_index})")
        uploaded_ids = {
            row["playbook_id"]
            for row in wave_results
            if row.get("status") in ("copied", "updated")
        }
        attempted = set(ready)
        pending_upload = [
            pb_id
            for pb_id in pending_upload
            if pb_id not in uploaded_ids and pb_id not in attempted
        ]
        if attempted and not uploaded_ids:
            op_warn(
                "Playbook upload wave %d failed for all %d playbook(s); stopping copy",
                wave_index,
                len(attempted),
                persistent=True,
            )
            break
        if pending_upload:
            playbook_name_to_id, playbook_id_to_name = _refresh_target_playbook_binding_maps(
                target,
                playbook_id_remap,
                force=True,
                source_names=source_names,
            )
            progress.complete_stage(f"Pause + Playbook Cache Refresh (Wave {wave_index})")

    op_info("Refreshing playbooks cache on %s after component copy", target.slug)
    refresh_playbooks_cache(target)
    progress.complete_stage("Final Playbook Cache Refresh")

    post_copy_diff_summary: dict[str, Any] | None = None
    if post_copy_diff:
        if script_results:
            ensure_scripts_cache(target, force=True)
        post_copy_diff_summary = apply_deep_copy_post_diffs(
            source=source,
            target=target,
            script_results=script_results,
            playbook_results=playbook_results,
            playbook_source_docs=playbook_source_docs,
            fetch_script=scripts_api.get_script,
            fetch_playbook=api.get_playbook,
        )

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

    out: dict[str, Any] = {
        "source_profile": source.slug,
        "target_profile": target.slug,
        "root_playbook_id": playbook_id,
        "root_playbook_name": plan["root_playbook_name"],
        "post_copy_diff": post_copy_diff,
        "telemetry": new_copy_run_telemetry(
            operation="playbooks.copy_components",
            post_copy_diff=post_copy_diff,
        ),
        "script_results": script_results,
        "playbook_results": playbook_results,
        "binding_issues": binding_issues,
        "script_id_remap": script_id_remap,
        "playbook_id_remap": playbook_id_remap,
        "warnings": plan.get("warnings") or [],
    }
    if post_copy_diff_summary is not None:
        out["post_copy_diff_summary"] = post_copy_diff_summary
        out["copy_diff_report"] = aggregate_copy_diff_report(out)
    return out
