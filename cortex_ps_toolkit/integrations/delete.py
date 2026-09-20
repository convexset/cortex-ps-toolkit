"""Delete custom integration definitions on a tenant."""

from __future__ import annotations

from typing import Any, Literal, Sequence

from ..core.client import TenantApiError
from ..credentials import CredentialProfile, get_profile
from ..platforms import assert_operation_supported
from . import api
from .metadata import integration_display_name, integration_key, is_deletable_integration
from .search_helpers import fetch_search_bundle, find_configuration, instances_for_configuration
from .service import refresh_integrations_cache

DeleteAction = Literal["delete", "blocked", "not_found"]


def plan_integrations_delete(profile: CredentialProfile | str, integration_ids: Sequence[str]) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    assert_operation_supported("integrations.delete", resolved.tenant_type)

    _data, lookup, instances = fetch_search_bundle(resolved)
    items: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for integration_id in integration_ids:
        configuration = find_configuration(lookup, integration_id)
        if not configuration:
            items.append({
                "integration_id": integration_id,
                "name": integration_id,
                "action": "not_found",
            })
            continue

        name = integration_key(configuration)
        display = integration_display_name(configuration)
        deletable, reason = is_deletable_integration(configuration)
        if not deletable:
            items.append({
                "integration_id": name,
                "name": display,
                "action": "blocked",
                "reason": reason,
            })
            continue

        matched_instances = instances_for_configuration(configuration, instances)
        item = {
            "integration_id": name,
            "name": display,
            "action": "delete",
            "instance_count": len(matched_instances),
            "instance_names": [str(instance.get("name") or instance.get("id") or "") for instance in matched_instances],
        }
        items.append(item)
        if matched_instances:
            warnings.append({
                "integration_id": name,
                "name": display,
                "instance_count": len(matched_instances),
                "instance_names": item["instance_names"],
            })

    counts = {
        "total": len(items),
        "delete": sum(1 for item in items if item["action"] == "delete"),
        "blocked": sum(1 for item in items if item["action"] == "blocked"),
        "not_found": sum(1 for item in items if item["action"] == "not_found"),
        "with_instances": sum(1 for item in items if item.get("instance_count")),
    }
    return {
        "profile": resolved.slug,
        "items": items,
        "counts": counts,
        "warnings": warnings,
        "has_instance_warnings": bool(warnings),
        "would_delete": counts["delete"] > 0,
    }


def delete_integrations(profile: CredentialProfile | str, integration_ids: Sequence[str]) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    assert_operation_supported("integrations.delete", resolved.tenant_type)

    plan = plan_integrations_delete(resolved, integration_ids)
    _data, lookup, _instances = fetch_search_bundle(resolved)
    results: list[dict[str, Any]] = []

    for item in plan["items"]:
        integration_id = str(item["integration_id"])
        name = str(item["name"])
        action = item["action"]
        if action == "not_found":
            results.append({
                "integration_id": integration_id,
                "name": name,
                "status": "not_found",
            })
            continue
        if action == "blocked":
            results.append({
                "integration_id": integration_id,
                "name": name,
                "status": "blocked",
                "reason": item.get("reason") or f"Integration {name!r} cannot be deleted",
            })
            continue

        configuration = find_configuration(lookup, integration_id)
        if not configuration:
            results.append({
                "integration_id": integration_id,
                "name": name,
                "status": "not_found",
            })
            continue

        try:
            delete_result = api.delete_integration_configuration(
                resolved,
                integration_id,
                configuration=configuration,
            )
            results.append({
                "integration_id": integration_id,
                "name": name,
                "status": "deleted",
                "instance_count": item.get("instance_count", 0),
                "response": delete_result.data,
                "status_code": delete_result.status_code,
            })
        except TenantApiError as exc:
            results.append({
                "integration_id": integration_id,
                "name": name,
                "status": "failed",
                "error": str(exc),
                "response": exc.body if isinstance(exc.body, dict) else {},
                "status_code": exc.status_code,
            })

    refresh_integrations_cache(resolved)
    return {
        "profile": resolved.slug,
        "results": results,
        "warnings": plan.get("warnings") or [],
    }
