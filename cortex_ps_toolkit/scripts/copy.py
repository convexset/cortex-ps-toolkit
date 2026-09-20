"""Copy scripts between credential profiles (tenants)."""

from __future__ import annotations

from typing import Any, Literal, Optional, Sequence

from ..cache.ensure import ensure_scripts_cache
from ..core.client import TenantApiError
from ..credentials import CredentialProfile, get_profile
from ..platforms import assert_operation_supported
from . import api
from .cache import find_script_in_index
from .metadata import is_copyable_script
from .service import refresh_scripts_cache
from ..ops_log import op_info
from .upload import save_script_document
from .copy_helpers import target_script_id_after_save

CopyAction = Literal["copy", "update", "skip", "conflict", "blocked_non_copyable"]


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


def resolve_script_meta(profile: CredentialProfile | str, script_id: str) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    entry = find_script_in_index(resolved, script_id=script_id)
    if not entry:
        refresh_scripts_cache(resolved)
        entry = find_script_in_index(resolved, script_id=script_id)
    if not entry:
        raise KeyError(f"Script not found: {script_id!r} on profile {resolved.slug}")
    return dict(entry)


def plan_scripts_copy(
    source_profile: str,
    target_profile: str,
    script_ids: Sequence[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
) -> dict[str, Any]:
    source = get_profile(source_profile)
    target = get_profile(target_profile)
    assert_operation_supported("scripts.copy", source.tenant_type)
    assert_operation_supported("scripts.copy", target.tenant_type)

    ensure_scripts_cache(target)

    items: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for script_id in script_ids:
        entry = resolve_script_meta(source, script_id)
        name = str(entry.get("name") or script_id)
        if not is_copyable_script(entry):
            items.append({
                "script_id": script_id,
                "name": name,
                "action": "blocked_non_copyable",
                "reason": (
                    "System script cannot be copied"
                    if entry.get("system") is True
                    else f"Content-pack script {name!r} is not copied"
                ),
            })
            continue
        existing = find_script_in_index(target, name=name)
        action = _classify_copy_action(
            existing=existing,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
        )
        item = {
            "script_id": script_id,
            "name": name,
            "action": action,
        }
        if existing:
            item["target_id"] = existing.get("id")
        items.append(item)
        if action == "conflict":
            conflicts.append(item)

    counts = {
        "total": len(items),
        "copy": sum(1 for item in items if item["action"] == "copy"),
        "update": sum(1 for item in items if item["action"] == "update"),
        "skip": sum(1 for item in items if item["action"] == "skip"),
        "conflict": len(conflicts),
        "blocked_non_copyable": sum(
            1 for item in items if item["action"] == "blocked_non_copyable"
        ),
    }
    would_abort = stop_on_conflict and bool(conflicts)

    return {
        "source_profile": source.slug,
        "target_profile": target.slug,
        "overwrite": overwrite,
        "stop_on_conflict": stop_on_conflict,
        "items": items,
        "counts": counts,
        "would_abort": would_abort,
        "conflicts": conflicts,
    }


def copy_scripts_to_tenant(
    source_profile: str,
    target_profile: str,
    script_ids: Sequence[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
) -> dict[str, Any]:
    source = get_profile(source_profile)
    target = get_profile(target_profile)
    assert_operation_supported("scripts.copy", source.tenant_type)
    assert_operation_supported("scripts.copy", target.tenant_type)

    plan = plan_scripts_copy(
        source_profile,
        target_profile,
        script_ids,
        overwrite=overwrite,
        stop_on_conflict=stop_on_conflict,
    )
    if plan["would_abort"]:
        conflict_names = ", ".join(item["name"] for item in plan["conflicts"])
        return {
            "source_profile": source.slug,
            "target_profile": target.slug,
            "aborted": True,
            "reason": (
                f"Stopped: {len(plan['conflicts'])} script(s) already exist on {target.slug}: "
                f"{conflict_names}"
            ),
            "conflicts": plan["conflicts"],
            "results": [],
        }

    results: list[dict[str, Any]] = []
    plan_by_id = {item["script_id"]: item for item in plan["items"]}
    for script_id in script_ids:
        item = plan_by_id[script_id]
        name = item["name"]
        action = item["action"]
        if action == "blocked_non_copyable":
            results.append({
                "script_id": script_id,
                "name": name,
                "status": "blocked",
                "reason": item.get("reason") or f"Script {name!r} is not copyable",
            })
            continue
        if action == "skip":
            skipped_target_id = str(item.get("target_id") or "")
            results.append({
                "script_id": script_id,
                "name": name,
                "status": "skipped",
                "target_script_id": skipped_target_id or None,
                "reason": f"Script {name!r} already exists on {target.slug}",
            })
            continue
        if action == "conflict":
            results.append({
                "script_id": script_id,
                "name": name,
                "status": "conflict",
                "reason": f"Script {name!r} already exists on {target.slug}",
            })
            continue

        overwrite_save = action == "update"
        target_script_id = str(item.get("target_id") or "") if overwrite_save else None
        script_doc = api.get_script(source, script_id)
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
            results.append({
                "script_id": script_id,
                "name": name,
                "status": "failed",
                "target_script_id": target_script_id or None,
                "error": str(exc),
                "response": exc.body if isinstance(exc.body, dict) else {},
                "status_code": exc.status_code,
            })
            continue
        resolved_target_id = target_script_id_after_save(
            target,
            name=name,
            saved=saved,
            fallback_id=target_script_id,
        )
        results.append({
            "script_id": script_id,
            "name": name,
            "status": "updated" if overwrite_save else "copied",
            "target_script_id": resolved_target_id or None,
            "response": saved,
            "status_code": status_code,
        })

    op_info("Refreshing scripts cache on %s after script copy", target.slug)
    refresh_scripts_cache(target)
    return {
        "source_profile": source.slug,
        "target_profile": target.slug,
        "results": results,
    }
