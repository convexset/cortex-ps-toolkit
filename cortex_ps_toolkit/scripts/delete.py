"""Delete scripts on a credential profile (tenant)."""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional, Sequence

from ..core.client import TenantApiError
from ..credentials import CredentialProfile, get_profile
from ..platforms import assert_operation_supported
from . import api
from .cache import find_script_in_index
from .service import refresh_scripts_cache

DeleteAction = Literal["delete", "blocked_system", "not_found"]


def is_system_script(entry: Mapping[str, Any]) -> bool:
    return entry.get("system") is True


def friendly_delete_error(exc: TenantApiError) -> str:
    message = str(exc)
    body = exc.body
    if isinstance(body, dict):
        for key in ("message", "error", "detail", "err_msg"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                message = value.strip()
                break
    lowered = message.lower()
    if "system" in lowered:
        return "System script cannot be deleted"
    return message


def _lookup_script(profile: CredentialProfile, script_id: str) -> Optional[dict[str, Any]]:
    entry = find_script_in_index(profile, script_id=script_id)
    if entry:
        return entry
    refresh_scripts_cache(profile)
    return find_script_in_index(profile, script_id=script_id)


def plan_scripts_delete(profile: CredentialProfile | str, script_ids: Sequence[str]) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    assert_operation_supported("scripts.copy", resolved.tenant_type)

    refresh_scripts_cache(resolved)

    items: list[dict[str, Any]] = []
    for script_id in script_ids:
        entry = _lookup_script(resolved, script_id)
        if not entry:
            items.append({
                "script_id": script_id,
                "name": script_id,
                "action": "not_found",
            })
            continue
        name = str(entry.get("name") or script_id)
        if is_system_script(entry):
            items.append({
                "script_id": script_id,
                "name": name,
                "action": "blocked_system",
            })
            continue
        items.append({
            "script_id": script_id,
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


def delete_scripts(profile: CredentialProfile | str, script_ids: Sequence[str]) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    assert_operation_supported("scripts.copy", resolved.tenant_type)

    plan = plan_scripts_delete(resolved, script_ids)
    results: list[dict[str, Any]] = []
    deleted_any = False

    for item in plan["items"]:
        script_id = str(item["script_id"])
        name = str(item["name"])
        action = item["action"]

        if action == "blocked_system":
            results.append({
                "script_id": script_id,
                "name": name,
                "status": "blocked",
                "reason": "System script cannot be deleted",
            })
            continue

        if action == "not_found":
            results.append({
                "script_id": script_id,
                "name": name,
                "status": "not_found",
                "reason": f"Script not found on {resolved.slug}",
            })
            continue

        try:
            _response, status_code = api.delete_script(resolved, script_id=script_id)
            deleted_any = True
            results.append({
                "script_id": script_id,
                "name": name,
                "status": "deleted",
                "status_code": status_code,
            })
        except TenantApiError as exc:
            results.append({
                "script_id": script_id,
                "name": name,
                "status": "failed",
                "reason": friendly_delete_error(exc),
                "status_code": exc.status_code,
            })

    if deleted_any:
        refresh_scripts_cache(resolved)

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
