"""Copy custom integration definitions between tenants."""

from __future__ import annotations

from typing import Any, Literal, Optional, Sequence

from ..core.client import TenantApiError
from ..credentials import CredentialProfile, get_profile
from ..ops_log import op_info
from ..platforms import assert_operation_supported
from . import api
from .metadata import integration_display_name, integration_key, is_copyable_integration
from .search_helpers import fetch_search_bundle, find_configuration
from .service import refresh_integrations_cache
from .yaml_export import configuration_to_yaml_text
from ..content.operation_plan import wrap_legacy_preview_plan
from ..content.post_copy_diff import (
    POST_COPY_DIFF_PROBE_ID,
    apply_post_copy_diffs,
    aggregate_copy_diff_report,
    new_copy_run_telemetry,
    summary_from_copy_diff_report,
)
from ..credentials import CredentialProfile
from .portable_yaml import configuration_to_portable_yaml_document
from .bundle_helpers import get_configuration_for_bundle

CopyAction = Literal["copy", "update", "skip", "conflict", "blocked"]


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


def plan_integrations_copy(
    source_profile: str,
    target_profile: str,
    integration_ids: Sequence[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
) -> dict[str, Any]:
    source = get_profile(source_profile)
    target = get_profile(target_profile)
    assert_operation_supported("integrations.copy", source.tenant_type)
    assert_operation_supported("integrations.copy", target.tenant_type)

    _source_data, source_lookup, _source_instances = fetch_search_bundle(source)
    _target_data, target_lookup, _target_instances = fetch_search_bundle(target)

    items: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for integration_id in integration_ids:
        configuration = find_configuration(source_lookup, integration_id)
        if not configuration:
            items.append({
                "integration_id": integration_id,
                "name": integration_id,
                "action": "blocked",
                "reason": f"Integration {integration_id!r} not found on {source.slug}",
            })
            continue

        name = integration_key(configuration)
        display = integration_display_name(configuration)
        copyable, reason = is_copyable_integration(configuration)
        if not copyable:
            items.append({
                "integration_id": name,
                "name": display,
                "action": "blocked",
                "reason": reason,
            })
            continue

        existing = find_configuration(target_lookup, name)
        action = _classify_copy_action(
            existing=existing,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
        )
        item = {
            "integration_id": name,
            "name": display,
            "action": action,
        }
        if existing:
            item["target_id"] = existing.get("id") or existing.get("name")
        items.append(item)
        if action == "conflict":
            conflicts.append(item)

    counts = {
        "total": len(items),
        "copy": sum(1 for item in items if item["action"] == "copy"),
        "update": sum(1 for item in items if item["action"] == "update"),
        "skip": sum(1 for item in items if item["action"] == "skip"),
        "conflict": len(conflicts),
        "blocked": sum(1 for item in items if item["action"] == "blocked"),
    }
    would_abort = stop_on_conflict and bool(conflicts)

    legacy = {
        "source_profile": source.slug,
        "target_profile": target.slug,
        "overwrite": overwrite,
        "stop_on_conflict": stop_on_conflict,
        "items": items,
        "counts": counts,
        "would_abort": would_abort,
        "conflicts": conflicts,
    }
    blocked = [item for item in items if item.get("action") == "blocked"]
    extra_warnings = None
    if blocked:
        extra_warnings = [
            {
                "code": "INTEGRATION_BLOCKED",
                "message": f"{len(blocked)} integration(s) cannot be copied (pack/system definitions or missing on source).",
            },
        ]
    return wrap_legacy_preview_plan(
        legacy,
        operation="integrations.copy",
        overwrite=overwrite,
        stop_on_conflict=stop_on_conflict,
        extra_warnings=extra_warnings,
    )


def _integration_portable_doc(profile: CredentialProfile, integration_id: str) -> dict[str, Any]:
    configuration = get_configuration_for_bundle(profile, integration_id)
    return configuration_to_portable_yaml_document(configuration)


def copy_integrations_to_tenant(
    source_profile: str,
    target_profile: str,
    integration_ids: Sequence[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    post_copy_diff: bool = False,
) -> dict[str, Any]:
    source = get_profile(source_profile)
    target = get_profile(target_profile)
    assert_operation_supported("integrations.copy", source.tenant_type)
    assert_operation_supported("integrations.copy", target.tenant_type)

    plan = plan_integrations_copy(
        source_profile,
        target_profile,
        integration_ids,
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
                f"Stopped: {len(plan['conflicts'])} integration(s) already exist on {target.slug}: "
                f"{conflict_names}"
            ),
            "conflicts": plan["conflicts"],
            "results": [],
        }

    _source_data, source_lookup, _source_instances = fetch_search_bundle(source)
    results: list[dict[str, Any]] = []
    diff_pending: list[tuple[int, dict[str, Any], str]] = []
    plan_by_id = {str(item["integration_id"]): item for item in plan["items"]}

    for integration_id in integration_ids:
        item = plan_by_id.get(str(integration_id))
        if not item:
            results.append({
                "integration_id": integration_id,
                "name": integration_id,
                "status": "failed",
                "error": "Integration was not included in copy plan",
            })
            continue

        name = str(item["name"])
        key = str(item["integration_id"])
        action = item["action"]
        if action == "blocked":
            results.append({
                "integration_id": key,
                "name": name,
                "status": "blocked",
                "reason": item.get("reason") or f"Integration {name!r} is not copyable",
            })
            continue
        if action == "skip":
            results.append({
                "integration_id": key,
                "name": name,
                "status": "skipped",
                "target_id": item.get("target_id"),
                "reason": f"Integration {name!r} already exists on {target.slug}",
            })
            continue
        if action == "conflict":
            results.append({
                "integration_id": key,
                "name": name,
                "status": "conflict",
                "reason": f"Integration {name!r} already exists on {target.slug}",
            })
            continue

        configuration = find_configuration(source_lookup, key)
        if not configuration:
            results.append({
                "integration_id": key,
                "name": name,
                "status": "failed",
                "error": f"Integration {key!r} not found on source",
            })
            continue

        source_portable = configuration_to_portable_yaml_document(configuration)
        yaml_text = configuration_to_yaml_text(configuration)
        filename = f"{key.replace('/', '_')}.yml"
        try:
            op_info(
                "Copying integration %r (%s) %s → %s [%s]",
                name,
                key,
                source.slug,
                target.slug,
                "overwrite" if action == "update" else "create",
            )
            upload_result = api.upload_integration_yaml(
                target,
                yaml_text.encode("utf-8"),
                filename=filename,
            )
            result_row = {
                "integration_id": key,
                "name": name,
                "status": "updated" if action == "update" else "copied",
                "target_id": item.get("target_id") or key,
                "response": upload_result.data,
                "status_code": upload_result.status_code,
            }
            results.append(result_row)
            if post_copy_diff:
                diff_pending.append((len(results) - 1, source_portable, name))
        except TenantApiError as exc:
            results.append({
                "integration_id": key,
                "name": name,
                "status": "failed",
                "error": str(exc),
                "response": exc.body if isinstance(exc.body, dict) else {},
                "status_code": exc.status_code,
            })

    op_info("Refreshing integrations cache on %s after integration copy", target.slug)
    refresh_integrations_cache(target)

    out: dict[str, Any] = {
        "source_profile": source.slug,
        "target_profile": target.slug,
        "results": results,
        "post_copy_diff": post_copy_diff,
        "telemetry": new_copy_run_telemetry(
            operation="integrations.copy",
            post_copy_diff=post_copy_diff,
        ),
    }
    if post_copy_diff and diff_pending:
        out["post_copy_diff_summary"] = apply_post_copy_diffs(
            results,
            target=target,
            kind="document",
            fetch=_integration_portable_doc,
            pending=diff_pending,
        )
        out["copy_diff_report"] = aggregate_copy_diff_report(out)
        if not out.get("post_copy_diff_summary"):
            out["post_copy_diff_summary"] = summary_from_copy_diff_report(out["copy_diff_report"])
        out["post_copy_diff_summary"]["probe"] = POST_COPY_DIFF_PROBE_ID
    return out
