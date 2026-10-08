"""Copy playbooks between credential profiles (tenants)."""

from __future__ import annotations

from typing import Any, Callable, Literal, Mapping, Optional, Sequence

from ..content.copy_modes import classify_copy_action
from ..content.copy_plan_params import effective_upload_name, normalize_copy_kwargs
from ..content.operation_plan import wrap_copy_plan

from ..content.post_copy_diff import (
    aggregate_copy_diff_report,
    apply_post_copy_diffs,
    new_copy_run_telemetry,
)
from ..core.batch_copy_progress import emit_copy_item_step, make_batch_copy_progress
from ..core.client import TenantApiError
from ..ops_log import op_action, op_info
from ..credentials import CredentialProfile, get_profile
from ..platforms import assert_operation_supported
from . import api
from .cache import find_playbook_in_index
from .service import refresh_playbooks_cache
from .upload import save_playbook_document

CopyAction = Literal["copy", "update", "skip", "conflict"]


def _classify_copy_action(
    *,
    existing: Optional[dict[str, Any]],
    overwrite: bool,
    stop_on_conflict: bool,
) -> CopyAction:
    if not existing:
        return "copy"
    if stop_on_conflict:
        return "conflict"
    if overwrite:
        return "update"
    return "skip"


def resolve_playbook_meta(profile: CredentialProfile | str, playbook_id: str) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    entry = find_playbook_in_index(resolved, playbook_id=playbook_id)
    if not entry:
        refresh_playbooks_cache(resolved)
        entry = find_playbook_in_index(resolved, playbook_id=playbook_id)
    if not entry:
        raise KeyError(f"Playbook not found: {playbook_id!r} on profile {resolved.slug}")
    return dict(entry)


def plan_playbooks_copy(
    source_profile: str,
    target_profile: str,
    playbook_ids: Sequence[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    copy_mode: Optional[str] = None,
    rename_suffix: str = "",
    rename_map: Optional[Mapping[str, str]] = None,
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

    refresh_playbooks_cache(target)

    items: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for playbook_id in playbook_ids:
        entry = resolve_playbook_meta(source, playbook_id)
        name = str(entry.get("name") or playbook_id)
        existing = find_playbook_in_index(target, name=name)
        action, extra = classify_copy_action(
            existing=existing,
            mode=mode,
            source_name=name,
            rename_suffix=rename_suffix,
            rename_map=rename_map,
            item_key=playbook_id,
            name_exists=lambda n: find_playbook_in_index(target, name=n),
            stop_on_conflict=stop_on_conflict,
        )
        item = {
            "playbook_id": playbook_id,
            "id": playbook_id,
            "name": name,
            "action": action,
            **extra,
        }
        if existing:
            item["target_id"] = existing.get("id")
        items.append(item)
        if action == "conflict":
            conflicts.append(item)

    counts = {
        "total": len(items),
        "copy": sum(1 for item in items if item["action"] in ("copy", "copy_as_new")),
        "update": sum(1 for item in items if item["action"] == "update"),
        "skip": sum(1 for item in items if item["action"] == "skip"),
        "conflict": len(conflicts),
        "copy_as_new": sum(1 for item in items if item["action"] == "copy_as_new"),
    }
    would_abort = (stop_on_conflict and bool(conflicts)) or (
        mode == "copy_as_new" and bool(conflicts)
    )

    legacy = {
        "source_profile": source.slug,
        "target_profile": target.slug,
        "overwrite": overwrite,
        "stop_on_conflict": stop_on_conflict,
        "copy_mode": mode,
        "rename_suffix": rename_suffix,
        "items": items,
        "counts": counts,
        "would_abort": would_abort,
        "conflicts": conflicts,
    }
    return wrap_copy_plan(legacy, operation="playbooks.copy", mode=mode, rename_suffix=rename_suffix)


def copy_playbooks_to_tenant(
    source_profile: str,
    target_profile: str,
    playbook_ids: Sequence[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    copy_mode: Optional[str] = None,
    rename_suffix: str = "",
    rename_map: Optional[Mapping[str, str]] = None,
    post_copy_diff: bool = False,
    on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    source = get_profile(source_profile)
    target = get_profile(target_profile)
    assert_operation_supported("playbooks.copy", source.tenant_type)
    assert_operation_supported("playbooks.copy", target.tenant_type)

    progress = make_batch_copy_progress(
        title="Playbooks Copy Progress",
        operation="playbooks.copy",
        on_progress=on_progress,
    )
    with op_action(
        "Playbooks copy %s → %s (%d playbook(s))",
        source.slug,
        target.slug,
        len(playbook_ids),
    ):
        plan = plan_playbooks_copy(
            source_profile,
            target_profile,
            playbook_ids,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
            copy_mode=copy_mode,
            rename_suffix=rename_suffix,
            rename_map=rename_map,
        )
        progress.complete_stage()
        if plan["would_abort"]:
            conflict_names = ", ".join(item["name"] for item in plan["conflicts"])
            return {
                "source_profile": source.slug,
                "target_profile": target.slug,
                "aborted": True,
                "reason": (
                    f"Stopped: {len(plan['conflicts'])} playbook(s) already exist on {target.slug}: "
                    f"{conflict_names}"
                ),
                "conflicts": plan["conflicts"],
                "results": [],
            }

        results: list[dict[str, Any]] = []
        diff_pending: list[tuple[int, dict[str, Any], str]] = []
        plan_by_id = {item["playbook_id"]: item for item in plan["items"]}
        total = len(playbook_ids)
        for index, playbook_id in enumerate(playbook_ids, start=1):
            item = plan_by_id[playbook_id]
            name = item["name"]
            action = item["action"]
            if action == "skip":
                results.append({
                    "playbook_id": playbook_id,
                    "name": name,
                    "status": "skipped",
                    "reason": f"Playbook {name!r} already exists on {target.slug}",
                })
                continue
            if action == "copy_as_new":
                name = effective_upload_name(item, fallback=name)
            if action == "conflict":
                results.append({
                    "playbook_id": playbook_id,
                    "name": name,
                    "status": "conflict",
                    "reason": f"Playbook {name!r} already exists on {target.slug}",
                })
                continue

            overwrite_save = action == "update"
            target_playbook_id = str(item.get("target_id") or "") if overwrite_save else None
            emit_copy_item_step(
                on_progress,
                source=source.slug,
                target=target.slug,
                item_label="playbook",
                name=name,
                index=index,
                total=total,
                item_id=playbook_id,
            )
            op_info(
                "Copying playbook %r (%s) %s → %s [%s]",
                name,
                playbook_id,
                source.slug,
                target.slug,
                "overwrite" if overwrite_save else "create",
            )
            playbook_doc = api.get_playbook(source, playbook_id)
            filename = f"{name.replace('/', '_')}.yml"
            try:
                saved, status_code, unresolved = save_playbook_document(
                    target,
                    playbook_doc,
                    filename=filename,
                    target_playbook_id=target_playbook_id or None,
                    overwrite=overwrite_save,
                    source_profile=source,
                )
            except TenantApiError as exc:
                results.append({
                    "playbook_id": playbook_id,
                    "name": name,
                    "status": "failed",
                    "target_playbook_id": target_playbook_id or None,
                    "error": str(exc),
                    "response": exc.body if isinstance(exc.body, dict) else {},
                    "status_code": exc.status_code,
                })
                continue
            results.append({
                "playbook_id": playbook_id,
                "name": name,
                "status": "updated" if overwrite_save else "copied",
                "target_playbook_id": target_playbook_id or saved.get("id") or saved.get("playbookId"),
                "response": saved,
                "status_code": status_code,
                "binding_unresolved": unresolved,
            })
            if post_copy_diff:
                diff_pending.append((len(results) - 1, playbook_doc, name))

        progress.complete_stage()
        op_info("Refreshing playbooks cache on %s after playbook copy", target.slug)
        refresh_playbooks_cache(target)
        progress.complete_stage()
        out: dict[str, Any] = {
            "source_profile": source.slug,
            "target_profile": target.slug,
            "post_copy_diff": post_copy_diff,
            "telemetry": new_copy_run_telemetry(operation="playbooks.copy", post_copy_diff=post_copy_diff),
            "results": results,
        }
        if post_copy_diff and diff_pending:
            out["post_copy_diff_summary"] = apply_post_copy_diffs(
                results,
                target=target,
                kind="playbook",
                fetch=api.get_playbook,
                pending=diff_pending,
            )
            out["copy_diff_report"] = aggregate_copy_diff_report(out)
        return out
