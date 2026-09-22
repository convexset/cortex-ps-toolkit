"""Playbook refactor orchestration (leaf/cluster extract + task error-handling updates)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Optional, Sequence

from ..credentials import get_profile
from ..paths import data_dir
from ..platforms import assert_operation_supported
from ..settings import max_inflight_per_host
from .refactor_mode import is_parallel_mode
from .refactor_bridge import (
    _ensure_imported,
    build_extract_multi_args,
    build_update_tasks_args,
    playbook_utils_runtime,
    progress_debug_sink,
    read_debug_result,
    temporary_credentials_file,
)
from .refactor_cache import (
    bootstrap_playbook_utils_cache_from_toolkit,
    load_task_update_targets_from_toolkit_cache,
    load_toolkit_playbook_body,
    resolve_toolkit_playbook_ref,
)
from .refactor_logging import emit_refactor_progress
from .refactor_overwrite import list_refactor_name_conflicts, validate_overwrite_request


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _debug_dir(label: str) -> Path:
    path = data_dir() / "refactor-debug" / f"{_utc_stamp()}-{label}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _parse_cluster_ref(playbook: Mapping[str, Any], spec: str) -> tuple[str, str]:
    if ":" not in spec:
        raise ValueError(f"Cluster spec must be START:END, got {spec!r}")
    start_ref, end_ref = spec.split(":", 1)
    start_ref = start_ref.strip()
    end_ref = end_ref.strip()
    if not start_ref or not end_ref:
        raise ValueError(f"Cluster spec must be START:END, got {spec!r}")
    from playbook_utils.inspect import resolve_task_ref

    return resolve_task_ref(playbook, start_ref), resolve_task_ref(playbook, end_ref)


def _resolve_playbook_ref(profile_slug: str, *, playbook_id: Optional[str], playbook_name: Optional[str]) -> str:
    if playbook_id:
        return playbook_id
    if playbook_name:
        return playbook_name
    raise ValueError("playbook_id or playbook_name is required")


def plan_refactor(
    profile_slug: str,
    *,
    playbook_id: Optional[str] = None,
    playbook_name: Optional[str] = None,
    leaf_tasks: Optional[Sequence[str]] = None,
    clusters: Optional[Sequence[str]] = None,
    post_task_updates: Optional[Sequence[str]] = None,
    parent_copy_name: Optional[str] = None,
    force: bool = False,
) -> dict[str, Any]:
    """Preflight refactor without tenant uploads."""
    leaf_tasks = list(leaf_tasks or [])
    clusters = list(clusters or [])
    post_task_updates = list(post_task_updates or [])
    if not leaf_tasks and not clusters:
        raise ValueError("At least one leaf task or cluster is required")

    if force:
        raise ValueError(
            "force=True is not supported for refactor preview; refresh Playbook Tools cache first."
        )
    profile = get_profile(profile_slug)
    assert_operation_supported("playbooks.refactor.extract_multi", profile.tenant_type)
    _ensure_imported()
    from playbook_utils.extract import (
        refactor_cluster_subplaybook_name,
        refactor_parent_copy_name,
        refactor_subplaybook_name,
    )
    from playbook_utils.graph import check_combined_extract
    from playbook_utils.inspect import resolve_task_ref
    from playbook_utils.keys import playbook_tasks, task_name

    playbook = load_toolkit_playbook_body(
        profile_slug, playbook_id=playbook_id, playbook_name=playbook_name
    )
    parent_name = str(playbook.get("name") or "playbook")
    tasks_map = playbook_tasks(playbook)

    task_ids = [resolve_task_ref(playbook, ref) for ref in leaf_tasks]
    cluster_pairs = [_parse_cluster_ref(playbook, spec) for spec in clusters]
    combined = check_combined_extract(playbook, task_ids, cluster_pairs)

    resolved_parent_copy_name = parent_copy_name or refactor_parent_copy_name(parent_name)
    extractions: list[dict[str, Any]] = []

    for cluster_check in combined.clusters:
        start_id = cluster_check.start_task_id
        end_id = cluster_check.end_task_id
        start_label = task_name(tasks_map[start_id]) or start_id
        end_label = task_name(tasks_map[end_id]) or end_id
        extractions.append(
            {
                "kind": "cluster",
                "start_task_id": start_id,
                "end_task_id": end_id,
                "start_label": start_label,
                "end_label": end_label,
                "subplaybook_name": refactor_cluster_subplaybook_name(
                    parent_name,
                    start_label,
                    end_label,
                    start_task_id=start_id,
                    end_task_id=end_id,
                ),
            }
        )

    for task_id, _root_check in zip(task_ids, combined.root_checks):
        task_label = task_name(tasks_map[task_id]) or task_id
        extractions.append(
            {
                "kind": "leaf",
                "task_id": task_id,
                "task_label": task_label,
                "subplaybook_name": refactor_subplaybook_name(parent_name, task_label, task_id=task_id),
            }
        )

    sub_names = [str(row["subplaybook_name"]) for row in extractions]
    existing_targets = list_refactor_name_conflicts(
        profile_slug,
        subplaybook_names=sub_names,
        parent_copy_name=resolved_parent_copy_name,
        source_playbook_id=str(playbook.get("id") or ""),
    )

    return {
        "profile": profile_slug,
        "platform": profile.tenant_type.value,
        "cache_only": True,
        "source_playbook": {
            "id": playbook.get("id"),
            "name": playbook.get("name"),
        },
        "parent_copy_name": resolved_parent_copy_name,
        "existing_targets": existing_targets,
        "overwrite_required": bool(existing_targets),
        "leaf_tasks": leaf_tasks,
        "clusters": clusters,
        "post_task_updates": post_task_updates,
        "ok": combined.ok,
        "reasons": list(combined.reasons),
        "extractions": extractions,
        "multi_extract_check": combined.to_dict(),
        "descriptions": (
            "Sub-playbooks and parent copy receive [REFACTOR-S]/[REFACTOR-M] names and "
            "refactor descriptions when execute succeeds (see playbook-utils)."
        ),
    }


def execute_refactor(
    profile_slug: str,
    *,
    playbook_id: Optional[str] = None,
    playbook_name: Optional[str] = None,
    leaf_tasks: Optional[Sequence[str]] = None,
    clusters: Optional[Sequence[str]] = None,
    post_task_updates: Optional[Sequence[str]] = None,
    parent_copy_name: Optional[str] = None,
    damp_run: bool = False,
    upload_only: bool = False,
    upload_parent_on_mismatch: bool = False,
    require_match: bool = False,
    force: bool = False,
    overwrite_existing: bool = True,
    overwrite_confirmed: bool = False,
    refactor_mode: Optional[str] = None,
    parallel_workers: Optional[int] = None,
    on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
    job_cache_key: Optional[str] = None,
) -> dict[str, Any]:
    """Run extract-multi (upload subs, compare, post-task updates, descriptions, parent copy)."""
    leaf_tasks = list(leaf_tasks or [])
    clusters = list(clusters or [])
    post_task_updates = list(post_task_updates or [])
    if not leaf_tasks and not clusters:
        raise ValueError("At least one leaf task or cluster is required")

    playbook_ref = _resolve_playbook_ref(profile_slug, playbook_id=playbook_id, playbook_name=playbook_name)
    profile = get_profile(profile_slug)
    assert_operation_supported("playbooks.refactor.extract_multi", profile.tenant_type)

    preflight = plan_refactor(
        profile_slug,
        playbook_id=playbook_id,
        playbook_name=playbook_name,
        leaf_tasks=leaf_tasks,
        clusters=clusters,
        post_task_updates=post_task_updates,
        parent_copy_name=parent_copy_name,
    )
    conflicts = list(preflight.get("existing_targets") or [])
    validate_overwrite_request(
        overwrite_existing=overwrite_existing,
        overwrite_confirmed=overwrite_confirmed,
        conflicts=conflicts,
    )

    _ensure_imported()
    from playbook_utils.cli import cmd_extract_multi

    debug_path = _debug_dir(f"extract-multi-{profile.slug}")
    started = time.monotonic()

    def _emit(phase: str, message: str, **extra: Any) -> None:
        emit_refactor_progress(phase, message)
        if on_progress:
            on_progress({"phase": phase, "message": message, **extra})

    parallel = is_parallel_mode(refactor_mode)
    workers = parallel_workers if parallel_workers is not None else max_inflight_per_host()
    variant = "parallel" if parallel else "sequential"
    job_key = job_cache_key or f"extract-multi-{profile.slug}-{int(started)}"
    _emit("start", f"Starting extract-multi ({variant}) for {playbook_ref}")
    with temporary_credentials_file(profile) as cred_path:
        with playbook_utils_runtime(
            profile_slug,
            operation_id="playbooks.refactor.extract_multi",
            job_cache_key=job_key,
        ) as (_p, _creds, _client, job_cache, _policy):
            seed_info = bootstrap_playbook_utils_cache_from_toolkit(
                job_cache,
                profile_slug,
                playbook_ref,
                existing_targets=conflicts,
            )
        _emit("cache", "Seeded job cache from toolkit bodies", **seed_info)
        args = build_extract_multi_args(
            credentials_path=str(cred_path),
            profile=profile,
            playbook=playbook_ref,
            leaf_tasks=leaf_tasks,
            clusters=clusters,
            post_task_updates=post_task_updates,
            parent_copy_name=parent_copy_name,
            debug_dir=str(debug_path),
            damp_run=damp_run,
            upload_only=upload_only,
            upload_parent_on_mismatch=upload_parent_on_mismatch,
            require_match=require_match,
            force=False,
            quiet=True,
            parallel=parallel,
            parallel_workers=workers,
            compare_after_parent=False,
            refresh_after_parent_upload=True,
            overwrite_existing=overwrite_existing,
            job_cache_key=job_key,
        )
        with progress_debug_sink(on_progress):
            exit_code = cmd_extract_multi(args)

    from ..server_config import copy_binding_cache_pause_seconds
    from .service import refresh_playbooks_cache

    pause = copy_binding_cache_pause_seconds()
    if pause > 0:
        _emit("refactor.pause", f"Pausing {pause:.0f}s before refreshing Playbook Tools cache")
        time.sleep(pause)
    _emit("refactor.toolkit_cache", "Refreshing Playbook Tools cache after refactor")
    refresh_info = refresh_playbooks_cache(profile)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    payload = read_debug_result(debug_path)
    payload["profile"] = profile_slug
    payload["exit_code"] = exit_code
    payload["ok"] = exit_code == 0
    payload["timing"] = {"total_elapsed_ms": elapsed_ms}
    payload["execution_variant"] = payload.get("execution_variant") or variant
    payload["job_cache_key"] = job_key
    payload["cache_seed"] = seed_info
    payload["toolkit_cache_refresh"] = refresh_info
    _emit("complete", f"Extract-multi ({variant}) finished exit_code={exit_code}", elapsed_ms=elapsed_ms)
    return payload


def plan_task_updates(
    profile_slug: str,
    *,
    playbook: Optional[str] = None,
    name_prefix: Optional[str] = None,
    updates: Optional[Sequence[str]] = None,
    context_updates: Optional[Sequence[str]] = None,
    match_task_names: Optional[Sequence[str]] = None,
    match_update: Optional[str] = None,
    force: bool = False,
) -> dict[str, Any]:
    """List target playbooks and validate update specs without uploading."""
    updates = list(updates or [])
    context_updates = list(context_updates or [])
    match_task_names = list(match_task_names or [])
    if not updates and not context_updates and not match_task_names:
        raise ValueError("At least one update, context_update, or match_task_name is required")
    if not playbook and not name_prefix:
        raise ValueError("playbook or name_prefix is required")

    profile = get_profile(profile_slug)
    assert_operation_supported("playbooks.refactor.update_tasks", profile.tenant_type)
    _ensure_imported()
    from playbook_utils.cli import _collect_error_updates_for_playbook
    from playbook_utils.error_retry import parse_context_update_spec, preflight_context_updates

    targets = load_task_update_targets_from_toolkit_cache(
        profile_slug,
        playbook=playbook,
        name_prefix=name_prefix,
        force=force,
    )
    outcomes: list[dict[str, Any]] = []
    for target in targets:
        playbook_name = str(target.get("name") or "")
        error_updates, error_rejected = _collect_error_updates_for_playbook(
            target,
            explicit_specs=updates,
            match_specs=match_task_names,
            match_actions=match_update,
        )
        context_requested = [parse_context_update_spec(spec) for spec in context_updates]
        _context_updates, context_rejected = preflight_context_updates(target, context_requested)
        outcomes.append(
            {
                "playbook_id": target.get("id"),
                "playbook_name": playbook_name,
                "error_update_count": len(error_updates),
                "error_rejected": error_rejected,
                "context_rejected": context_rejected,
                "would_apply": bool(error_updates or _context_updates)
                and not error_rejected
                and not context_rejected,
            }
        )

    return {
        "profile": profile_slug,
        "platform": profile.tenant_type.value,
        "cache_only": True,
        "target_count": len(targets),
        "targets": outcomes,
        "ok": all(row.get("would_apply") or row.get("error_rejected") == [] for row in outcomes),
    }


def execute_task_updates(
    profile_slug: str,
    *,
    playbook: Optional[str] = None,
    name_prefix: Optional[str] = None,
    updates: Optional[Sequence[str]] = None,
    context_updates: Optional[Sequence[str]] = None,
    match_task_names: Optional[Sequence[str]] = None,
    match_update: Optional[str] = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Apply in-place retry/error-handling or context-sharing updates."""
    profile = get_profile(profile_slug)
    assert_operation_supported("playbooks.refactor.update_tasks", profile.tenant_type)

    _ensure_imported()
    from playbook_utils.cli import cmd_update_playbook_tasks

    debug_path = _debug_dir(f"update-tasks-{profile.slug}")
    with temporary_credentials_file(profile) as cred_path:
        args = build_update_tasks_args(
            credentials_path=str(cred_path),
            profile=profile,
            playbook=playbook,
            name_prefix=name_prefix,
            updates=list(updates or []),
            context_updates=list(context_updates or []),
            match_task_names=list(match_task_names or []),
            match_update=match_update,
            debug_dir=str(debug_path),
            dry_run=dry_run,
            force=force,
        )
        with progress_debug_sink(None):
            exit_code = cmd_update_playbook_tasks(args)

    payload = read_debug_result(debug_path)
    payload["profile"] = profile_slug
    payload["exit_code"] = exit_code
    payload["ok"] = exit_code == 0
    payload["dry_run"] = dry_run
    return payload
