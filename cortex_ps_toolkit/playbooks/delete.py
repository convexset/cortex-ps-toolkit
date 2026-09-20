"""Delete playbooks on a credential profile (tenant)."""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional, Sequence

from ..core.client import TenantApiError
from ..cache.ensure import ensure_playbooks_cache
from ..credentials import CredentialProfile, get_profile
from ..platforms import assert_operation_supported
from . import api
from .cache import find_playbook_in_index
from .service import refresh_playbooks_cache

DeleteAction = Literal["delete", "blocked_system", "not_found"]


def is_system_playbook(entry: Mapping[str, Any]) -> bool:
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
        return "System playbook cannot be deleted"
    return message


def _lookup_playbook(profile: CredentialProfile, playbook_id: str) -> Optional[dict[str, Any]]:
    entry = find_playbook_in_index(profile, playbook_id=playbook_id)
    if entry:
        return entry
    refresh_playbooks_cache(profile)
    return find_playbook_in_index(profile, playbook_id=playbook_id)


def plan_playbooks_delete(profile: CredentialProfile | str, playbook_ids: Sequence[str]) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    assert_operation_supported("playbooks.copy", resolved.tenant_type)

    ensure_playbooks_cache(resolved)

    items: list[dict[str, Any]] = []
    for playbook_id in playbook_ids:
        entry = _lookup_playbook(resolved, playbook_id)
        if not entry:
            items.append({
                "playbook_id": playbook_id,
                "name": playbook_id,
                "action": "not_found",
            })
            continue
        name = str(entry.get("name") or playbook_id)
        if is_system_playbook(entry):
            items.append({
                "playbook_id": playbook_id,
                "name": name,
                "action": "blocked_system",
            })
            continue
        items.append({
            "playbook_id": playbook_id,
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


def delete_playbooks(profile: CredentialProfile | str, playbook_ids: Sequence[str]) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    assert_operation_supported("playbooks.copy", resolved.tenant_type)

    plan = plan_playbooks_delete(resolved, playbook_ids)
    results: list[dict[str, Any]] = []
    deleted_any = False

    for item in plan["items"]:
        playbook_id = str(item["playbook_id"])
        name = str(item["name"])
        action = item["action"]

        if action == "blocked_system":
            results.append({
                "playbook_id": playbook_id,
                "name": name,
                "status": "blocked",
                "reason": "System playbook cannot be deleted",
            })
            continue

        if action == "not_found":
            results.append({
                "playbook_id": playbook_id,
                "name": name,
                "status": "not_found",
                "reason": f"Playbook not found on {resolved.slug}",
            })
            continue

        try:
            _response, status_code = api.delete_playbook(resolved, playbook_id=playbook_id)
            deleted_any = True
            results.append({
                "playbook_id": playbook_id,
                "name": name,
                "status": "deleted",
                "status_code": status_code,
            })
        except TenantApiError as exc:
            results.append({
                "playbook_id": playbook_id,
                "name": name,
                "status": "failed",
                "reason": friendly_delete_error(exc),
                "status_code": exc.status_code,
            })

    if deleted_any:
        refresh_playbooks_cache(resolved)

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
