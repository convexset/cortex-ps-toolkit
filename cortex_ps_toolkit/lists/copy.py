"""Copy lists between credential profiles (tenants)."""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional, Sequence

from ..credentials import CredentialProfile, get_profile
from ..platforms import assert_operation_supported
from . import api
from .cache import find_list_in_index
from .service import refresh_lists_cache, save_list

CopyAction = Literal["copy", "update", "skip", "conflict"]


def normalize_list_data(raw: Any, fallback: str = "") -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        if not raw:
            return ""
        return "\n".join(str(item) for item in raw)
    if raw is None:
        return fallback
    return str(raw)


def list_data_needs_download(entry: Mapping[str, Any]) -> bool:
    if entry.get("truncated"):
        return True
    raw = entry.get("data")
    if raw is None:
        return True
    if isinstance(raw, str):
        return raw == ""
    return False


def resolve_list_meta(profile: CredentialProfile | str, list_id: str) -> dict[str, Any]:
    """Resolve list metadata from cache (name, type, …) without downloading body."""
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    entry = find_list_in_index(resolved, list_id=list_id)
    if not entry:
        refresh_lists_cache(resolved)
        entry = find_list_in_index(resolved, list_id=list_id)
    if not entry:
        raise KeyError(f"List not found: {list_id!r} on profile {resolved.slug}")
    return dict(entry)


def resolve_list_entry(profile: CredentialProfile | str, list_id: str) -> dict[str, Any]:
    entry = resolve_list_meta(profile, list_id)
    raw = entry.get("data")
    if list_data_needs_download(entry):
        resolved = get_profile(profile) if isinstance(profile, str) else profile
        raw = api.download_list_data(resolved, list_id)
    result = dict(entry)
    result["data"] = normalize_list_data(raw, "")
    return result


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


def plan_lists_copy(
    source_profile: str,
    target_profile: str,
    list_ids: Sequence[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
) -> dict[str, Any]:
    """Preview a copy operation after refreshing the target cache."""
    source = get_profile(source_profile)
    target = get_profile(target_profile)
    assert_operation_supported("content.lists.manage", source.tenant_type)
    assert_operation_supported("content.lists.manage", target.tenant_type)

    refresh_lists_cache(target)

    items: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for list_id in list_ids:
        entry = resolve_list_meta(source, list_id)
        name = str(entry.get("name") or list_id)
        existing = find_list_in_index(target, name=name)
        action = _classify_copy_action(
            existing=existing,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
        )
        item = {
            "list_id": list_id,
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


def copy_lists_to_tenant(
    source_profile: str,
    target_profile: str,
    list_ids: Sequence[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
) -> dict[str, Any]:
    source = get_profile(source_profile)
    target = get_profile(target_profile)
    assert_operation_supported("content.lists.manage", source.tenant_type)
    assert_operation_supported("content.lists.manage", target.tenant_type)

    plan = plan_lists_copy(
        source_profile,
        target_profile,
        list_ids,
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
                f"Stopped: {len(plan['conflicts'])} list(s) already exist on {target.slug}: "
                f"{conflict_names}"
            ),
            "conflicts": plan["conflicts"],
            "results": [],
        }

    results: list[dict[str, Any]] = []
    plan_by_id = {item["list_id"]: item for item in plan["items"]}
    for list_id in list_ids:
        item = plan_by_id[list_id]
        name = item["name"]
        action = item["action"]
        if action == "skip":
            results.append({
                "list_id": list_id,
                "name": name,
                "status": "skipped",
                "reason": f"List {name!r} already exists on {target.slug}",
            })
            continue
        if action == "conflict":
            results.append({
                "list_id": list_id,
                "name": name,
                "status": "conflict",
                "reason": f"List {name!r} already exists on {target.slug}",
            })
            continue

        entry = resolve_list_entry(source, list_id)
        list_type = str(entry.get("type") or "plain_text")
        description = str(entry.get("description") or "")
        data = normalize_list_data(entry.get("data"), "")

        overwrite_save = action == "update"
        target_id = str(item.get("target_id") or "") if overwrite_save else None
        saved, status_code = save_list(
            target,
            name=name,
            data=data,
            list_type=list_type,
            description=description,
            list_id=target_id or None,
        )
        results.append({
            "list_id": list_id,
            "name": name,
            "status": "updated" if overwrite_save else "copied",
            "target_id": saved.get("id") or target_id,
            "status_code": status_code,
        })

    return {
        "source_profile": source.slug,
        "target_profile": target.slug,
        "results": results,
    }
