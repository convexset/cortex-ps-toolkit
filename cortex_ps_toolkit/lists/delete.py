"""Delete lists on a credential profile (tenant)."""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional, Sequence

from ..core.client import TenantApiError
from ..credentials import CredentialProfile, get_profile
from ..platforms import assert_operation_supported
from . import api
from .cache import find_list_in_index
from .service import refresh_lists_cache

DeleteAction = Literal["delete", "blocked_system", "not_found"]


def is_system_list(entry: Mapping[str, Any]) -> bool:
    return entry.get("system") is True


def friendly_delete_error(exc: TenantApiError) -> str:
    message = str(exc)
    body = exc.body
    if isinstance(body, dict):
        for key in ("message", "error", "detail"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                message = value.strip()
                break
    lowered = message.lower()
    if "system" in lowered:
        return "System list cannot be deleted"
    return message


def _lookup_list(profile: CredentialProfile, list_id: str) -> Optional[dict[str, Any]]:
    entry = find_list_in_index(profile, list_id=list_id)
    if entry:
        return entry
    refresh_lists_cache(profile)
    return find_list_in_index(profile, list_id=list_id)


def plan_lists_delete(profile: CredentialProfile | str, list_ids: Sequence[str]) -> dict[str, Any]:
    """Preview deletions after refreshing the profile cache."""
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    assert_operation_supported("content.lists.manage", resolved.tenant_type)

    refresh_lists_cache(resolved)

    items: list[dict[str, Any]] = []
    for list_id in list_ids:
        entry = _lookup_list(resolved, list_id)
        if not entry:
            items.append({
                "list_id": list_id,
                "name": list_id,
                "action": "not_found",
            })
            continue
        name = str(entry.get("name") or list_id)
        if is_system_list(entry):
            items.append({
                "list_id": list_id,
                "name": name,
                "action": "blocked_system",
            })
            continue
        items.append({
            "list_id": list_id,
            "name": name,
            "action": "delete",
        })

    counts = {
        "total": len(items),
        "delete": sum(1 for item in items if item["action"] == "delete"),
        "blocked_system": sum(1 for item in items if item["action"] == "blocked_system"),
        "not_found": sum(1 for item in items if item["action"] == "not_found"),
    }
    return {
        "profile": resolved.slug,
        "items": items,
        "counts": counts,
        "would_delete": counts["delete"] > 0,
    }


def delete_lists(profile: CredentialProfile | str, list_ids: Sequence[str]) -> dict[str, Any]:
    """Delete selected lists; skip system lists and report per-item outcomes."""
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    assert_operation_supported("content.lists.manage", resolved.tenant_type)

    plan = plan_lists_delete(resolved, list_ids)
    results: list[dict[str, Any]] = []
    deleted_any = False

    for item in plan["items"]:
        list_id = str(item["list_id"])
        name = str(item["name"])
        action = item["action"]

        if action == "blocked_system":
            results.append({
                "list_id": list_id,
                "name": name,
                "status": "blocked",
                "reason": "System list cannot be deleted",
            })
            continue

        if action == "not_found":
            results.append({
                "list_id": list_id,
                "name": name,
                "status": "not_found",
                "reason": f"List not found on {resolved.slug}",
            })
            continue

        try:
            _response, status_code = api.delete_list_by_id(resolved, list_id)
            deleted_any = True
            results.append({
                "list_id": list_id,
                "name": name,
                "status": "deleted",
                "status_code": status_code,
            })
        except TenantApiError as exc:
            results.append({
                "list_id": list_id,
                "name": name,
                "status": "failed",
                "reason": friendly_delete_error(exc),
                "status_code": exc.status_code,
            })

    if deleted_any:
        refresh_lists_cache(resolved)

    counts = {
        "total": len(results),
        "deleted": sum(1 for item in results if item["status"] == "deleted"),
        "blocked": sum(1 for item in results if item["status"] == "blocked"),
        "failed": sum(1 for item in results if item["status"] == "failed"),
        "not_found": sum(1 for item in results if item["status"] == "not_found"),
    }
    return {
        "profile": resolved.slug,
        "results": results,
        "counts": counts,
    }
