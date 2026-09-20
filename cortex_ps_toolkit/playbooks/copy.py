"""Copy playbooks between credential profiles (tenants)."""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional, Sequence

from ..core.client import TenantApiError
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
) -> dict[str, Any]:
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
        action = _classify_copy_action(
            existing=existing,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
        )
        item = {
            "playbook_id": playbook_id,
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


def copy_playbooks_to_tenant(
    source_profile: str,
    target_profile: str,
    playbook_ids: Sequence[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
) -> dict[str, Any]:
    source = get_profile(source_profile)
    target = get_profile(target_profile)
    assert_operation_supported("playbooks.copy", source.tenant_type)
    assert_operation_supported("playbooks.copy", target.tenant_type)

    plan = plan_playbooks_copy(
        source_profile,
        target_profile,
        playbook_ids,
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
                f"Stopped: {len(plan['conflicts'])} playbook(s) already exist on {target.slug}: "
                f"{conflict_names}"
            ),
            "conflicts": plan["conflicts"],
            "results": [],
        }

    results: list[dict[str, Any]] = []
    plan_by_id = {item["playbook_id"]: item for item in plan["items"]}
    for playbook_id in playbook_ids:
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

    refresh_playbooks_cache(target)
    return {
        "source_profile": source.slug,
        "target_profile": target.slug,
        "results": results,
    }
