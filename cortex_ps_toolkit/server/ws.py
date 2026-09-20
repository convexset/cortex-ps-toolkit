"""WebSocket endpoint: server push + background job requests."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from starlette.websockets import WebSocket, WebSocketDisconnect

from ..runtime.graph import RefreshMode
from ..workflows.cache_refresh import (
    graph_result_to_dict,
    refresh_content_scopes_parallel,
    refresh_integrations_scopes_parallel,
    ws_scope_names,
)
from ..core.long_op_progress import LongOperationProgress
from ..design_content.copy import copy_assets_to_tenant
from ..design_content.delete import delete_assets
from ..design_content.orchestrator import execute_cross_tenant_workflow
from ..design_content.service import refresh_all_cache, refresh_asset_cache
from ..design_content.types import ASSET_KINDS
from ..platform_admin import api as platform_admin_api
from ..platform_admin.bioc_copy import copy_biocs_to_tenant
from ..platform_admin.copy import copy_correlation_rules_to_tenant
from ..platform_admin.indicator_copy import copy_indicators_to_tenant
from ..credentials import get_profile
from ..platform_admin.service import refresh_all_cache as refresh_platform_admin_cache
from ..platform_admin.service import refresh_section_cache as refresh_platform_admin_section
from ..platform_admin.types import ADMIN_SECTIONS
from ..playbooks.refactor import execute_refactor
from ..playbooks.refactor_workflow import execute_refactor_workflow
from .copy_notifications import (
    maybe_publish_item_copied_from_progress,
    publish_object_bundle_complete_notification,
)
from .delete_notifications import publish_delete_success_notifications
from .events import broadcast, publish, publish_notification, subscribe, unsubscribe


async def _run_cache_refresh(job_id: str, payload: dict[str, Any]) -> None:
    profile = str(payload.get("profile") or "")
    scope = str(payload.get("scope") or "playbooks").lower()
    if not profile:
        await broadcast({
            "type": "job.failed",
            "job_id": job_id,
            "action": "cache.refresh",
            "error": "profile required",
        })
        publish_notification("Cache refresh failed: profile required", level="error")
        return

    await broadcast({
        "type": "job.started",
        "job_id": job_id,
        "action": "cache.refresh",
        "payload": {"profile": profile, "scope": scope},
    })
    publish_notification(f"Refreshing {scope} cache for {profile}…", level="info", auto_dismiss_ms=5000)

    def on_progress(event: dict[str, Any]) -> None:
        _publish_job_progress(job_id, "cache.refresh", event)

    try:
        scope_names = ws_scope_names(scope)
        content_scopes = [name for name in scope_names if name != "integrations"]
        integration_scopes = ["commands", "instances", "tenant_credentials", "contentpacks"]
        pending = [
            {"scope": name, "status": "pending"}
            for name in (content_scopes + (["integrations"] if "integrations" in scope_names else []))
        ]

        results: dict[str, Any] = {"profile": profile, "scope": scope}
        with LongOperationProgress(on_progress, action="cache.refresh") as progress:
            progress.set_in_flight(pending)
            if content_scopes:
                progress.set_current(scope="content", scopes=content_scopes, status="running")
                content_result = await asyncio.to_thread(
                    refresh_content_scopes_parallel,
                    profile,
                    content_scopes,
                    mode=RefreshMode.ELECTIVE,
                )
                for task_id, state in content_result.tasks.items():
                    if state.status == "success":
                        results[task_id] = state.result
                    else:
                        results[task_id] = {
                            "error": state.error,
                            "failed_dependencies": state.failed_dependencies,
                        }
                    for item in pending:
                        if item["scope"] == task_id:
                            item["status"] = state.status
                progress.set_in_flight(pending)
            if "integrations" in scope_names:
                progress.set_current(scope="integrations", status="running")
                integration_result = await asyncio.to_thread(
                    refresh_integrations_scopes_parallel,
                    profile,
                    integration_scopes,
                    mode=RefreshMode.ELECTIVE,
                )
                results["integrations"] = graph_result_to_dict(integration_result)
                for item in pending:
                    if item["scope"] == "integrations":
                        item["status"] = "success"
                progress.set_in_flight(pending)
            progress.set_current(status="completed")

        await broadcast({
            "type": "job.completed",
            "job_id": job_id,
            "action": "cache.refresh",
            "result": results,
        })
        publish_notification(
            f"Cache refresh complete for {profile} ({scope})",
            level="success",
        )
    except Exception as exc:
        await broadcast({
            "type": "job.failed",
            "job_id": job_id,
            "action": "cache.refresh",
            "error": str(exc),
        })
        publish_notification(f"Cache refresh failed: {exc}", level="error")


def _publish_job_progress(job_id: str, action: str, event: dict[str, Any]) -> None:
    publish({
        "type": "job.progress",
        "job_id": job_id,
        "action": action,
        **event,
    })


async def _run_refactor_execute(job_id: str, payload: dict[str, Any]) -> None:
    profile = str(payload.get("profile") or "")
    if not profile:
        await broadcast({
            "type": "job.failed",
            "job_id": job_id,
            "action": "playbooks.refactor.execute",
            "error": "profile required",
        })
        return

    await broadcast({
        "type": "job.started",
        "job_id": job_id,
        "action": "playbooks.refactor.execute",
        "payload": {"profile": profile},
    })
    publish_notification(f"Refactor started for {profile}…", level="info", auto_dismiss_ms=0)

    def on_progress(event: dict[str, Any]) -> None:
        _publish_job_progress(job_id, "playbooks.refactor.execute", event)

    try:
        kwargs: dict[str, Any] = {
            "leaf_tasks": list(payload.get("leaf_tasks") or []),
            "clusters": list(payload.get("clusters") or []),
            "post_task_updates": list(payload.get("post_task_updates") or []),
            "damp_run": bool(payload.get("damp_run")),
            "upload_only": bool(payload.get("upload_only")),
            "upload_parent_on_mismatch": bool(payload.get("upload_parent_on_mismatch")),
            "require_match": bool(payload.get("require_match")),
            "force": bool(payload.get("force")),
            "on_progress": on_progress,
        }
        if payload.get("playbook_id"):
            kwargs["playbook_id"] = str(payload.get("playbook_id"))
        if payload.get("playbook_name"):
            kwargs["playbook_name"] = str(payload.get("playbook_name"))
        if payload.get("parent_copy_name"):
            kwargs["parent_copy_name"] = str(payload.get("parent_copy_name"))
        if payload.get("refactor_mode"):
            kwargs["refactor_mode"] = str(payload.get("refactor_mode"))
        result = await asyncio.to_thread(execute_refactor, profile, **kwargs)
        await broadcast({
            "type": "job.completed",
            "job_id": job_id,
            "action": "playbooks.refactor.execute",
            "result": result,
        })
        level = "success" if result.get("ok") else "error"
        publish_notification(
            f"Refactor {'complete' if result.get('ok') else 'finished with issues'} for {profile}",
            level=level,
        )
    except Exception as exc:
        await broadcast({
            "type": "job.failed",
            "job_id": job_id,
            "action": "playbooks.refactor.execute",
            "error": str(exc),
        })
        publish_notification(f"Refactor failed: {exc}", level="error")


async def _run_refactor_workflow(job_id: str, payload: dict[str, Any]) -> None:
    preset_id = str(payload.get("preset_id") or payload.get("preset") or "")
    if not preset_id:
        await broadcast({
            "type": "job.failed",
            "job_id": job_id,
            "action": "playbooks.refactor.workflow",
            "error": "preset_id required",
        })
        return

    await broadcast({
        "type": "job.started",
        "job_id": job_id,
        "action": "playbooks.refactor.workflow",
        "payload": {"preset_id": preset_id},
    })
    publish_notification(f"Refactor workflow {preset_id} started…", level="info", auto_dismiss_ms=0)

    def on_progress(event: dict[str, Any]) -> None:
        _publish_job_progress(job_id, "playbooks.refactor.workflow", event)

    try:
        workflow_kwargs: dict[str, Any] = {
            "skip_clear": bool(payload.get("skip_clear")),
            "on_progress": on_progress,
        }
        if payload.get("refactor_mode"):
            workflow_kwargs["refactor_mode"] = str(payload.get("refactor_mode"))
        result = await asyncio.to_thread(
            execute_refactor_workflow,
            preset_id,
            **workflow_kwargs,
        )
        await broadcast({
            "type": "job.completed",
            "job_id": job_id,
            "action": "playbooks.refactor.workflow",
            "result": result,
        })
        level = "success" if result.get("ok") else "error"
        publish_notification(
            f"Workflow {'complete' if result.get('ok') else 'finished with issues'} ({preset_id})",
            level=level,
        )
    except Exception as exc:
        await broadcast({
            "type": "job.failed",
            "job_id": job_id,
            "action": "playbooks.refactor.workflow",
            "error": str(exc),
        })
        publish_notification(f"Refactor workflow failed: {exc}", level="error")


async def _run_design_content_refresh(job_id: str, payload: dict[str, Any]) -> None:
    profile = str(payload.get("profile") or "")
    asset_raw = payload.get("asset")
    if not profile:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "design_content.refresh", "error": "profile required"})
        return
    await broadcast({"type": "job.started", "job_id": job_id, "action": "design_content.refresh", "payload": payload})
    publish_notification(f"Refreshing design content for {profile}…", level="info", auto_dismiss_ms=0)

    def on_progress(event: dict[str, Any]) -> None:
        _publish_job_progress(job_id, "design_content.refresh", event)

    try:
        with LongOperationProgress(on_progress, action="design_content.refresh") as progress:
            if asset_raw:
                asset = str(asset_raw)
                if asset not in ASSET_KINDS:
                    raise ValueError(f"asset must be one of: {', '.join(ASSET_KINDS)}")
                progress.set_current(asset=asset, status="running")
                result = await asyncio.to_thread(refresh_asset_cache, profile, asset)  # type: ignore[arg-type]
            else:
                progress.set_in_flight([{"asset": asset, "status": "pending"} for asset in ASSET_KINDS])
                result = await asyncio.to_thread(refresh_all_cache, profile)
            progress.set_current(status="completed")
        await broadcast({"type": "job.completed", "job_id": job_id, "action": "design_content.refresh", "result": result})
        publish_notification(f"Design content refresh complete for {profile}", level="success")
    except Exception as exc:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "design_content.refresh", "error": str(exc)})
        publish_notification(f"Design content refresh failed: {exc}", level="error")


async def _run_design_content_copy(job_id: str, payload: dict[str, Any]) -> None:
    source = str(payload.get("source_profile") or "")
    target = str(payload.get("target_profile") or "")
    asset = str(payload.get("asset") or "")
    item_ids = [str(item) for item in (payload.get("item_ids") or [])]
    if not source or not target or not asset or not item_ids:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "design_content.copy", "error": "source_profile, target_profile, asset, item_ids required"})
        return
    await broadcast({"type": "job.started", "job_id": job_id, "action": "design_content.copy", "payload": payload})
    publish_notification(f"Copying {asset} from {source} to {target}…", level="info", auto_dismiss_ms=0)

    def on_progress(event: dict[str, Any]) -> None:
        _publish_job_progress(job_id, "design_content.copy", event)
        maybe_publish_item_copied_from_progress(
            event,
            source=source,
            target=target,
            title=f"Copy {asset}",
        )

    try:
        with LongOperationProgress(on_progress, action="design_content.copy") as progress:
            progress.set_current(source=source, target=target, asset=asset, item_count=len(item_ids))
            progress.set_in_flight([{"item_id": item_id, "status": "pending"} for item_id in item_ids])
            result = await asyncio.to_thread(
                copy_assets_to_tenant,
                source,
                target,
                asset,  # type: ignore[arg-type]
                item_ids,
                overwrite=bool(payload.get("overwrite")),
                stop_on_conflict=bool(payload.get("stop_on_conflict")),
                name_suffix=payload.get("name_suffix"),
                prefer_direct_on_xsoar6=bool(payload.get("prefer_direct_on_xsoar6", True)),
                on_progress=on_progress,
            )
        await broadcast({"type": "job.completed", "job_id": job_id, "action": "design_content.copy", "result": result})
        if not result.get("executed"):
            publish_notification(
                result.get("error") or f"Copy {asset} finished with issues",
                level="error",
                title=f"Copy {asset}",
                auto_dismiss_ms=5000,
            )
    except Exception as exc:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "design_content.copy", "error": str(exc)})
        publish_notification(f"Design content copy failed: {exc}", level="error", auto_dismiss_ms=5000)


async def _run_design_content_orchestrate(job_id: str, payload: dict[str, Any]) -> None:
    source = str(payload.get("source_profile") or "")
    target = str(payload.get("target_profile") or "")
    selections = payload.get("selections") or {}
    if not source or not target or not isinstance(selections, dict):
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "design_content.orchestrate", "error": "source_profile, target_profile, selections required"})
        return
    await broadcast({"type": "job.started", "job_id": job_id, "action": "design_content.orchestrate", "payload": payload})
    publish_notification(
        f"Copying Object Bundle from {source} to {target}…",
        level="info",
        auto_dismiss_ms=5000,
    )

    def on_progress(event: dict[str, Any]) -> None:
        _publish_job_progress(job_id, "design_content.orchestrate", event)
        maybe_publish_item_copied_from_progress(
            event,
            source=source,
            target=target,
            title="Object Bundle copy",
        )

    try:
        result = await asyncio.to_thread(
            execute_cross_tenant_workflow,
            source,
            target,
            {str(k): [str(item) for item in v] for k, v in selections.items()},
            overwrite=bool(payload.get("overwrite")),
            stop_on_conflict=bool(payload.get("stop_on_conflict")),
            name_suffix=payload.get("name_suffix"),
            prefer_direct_on_xsoar6=bool(payload.get("prefer_direct_on_xsoar6", True)),
            include_correlation_rules=bool(payload.get("include_correlation_rules")),
            correlation_rule_names=[str(item) for item in (payload.get("correlation_rule_names") or [])],
            on_progress=on_progress,
        )
        await broadcast({"type": "job.completed", "job_id": job_id, "action": "design_content.orchestrate", "result": result})
        if result.get("executed"):
            publish_object_bundle_complete_notification(
                result,
                source=source,
                target=target,
            )
        else:
            publish_notification(
                result.get("halt_reason") or "Object Bundle copy finished with issues",
                level="error",
                title="Object Bundle copy",
                auto_dismiss_ms=5000,
            )
    except Exception as exc:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "design_content.orchestrate", "error": str(exc)})
        publish_notification(f"Object Bundle copy failed: {exc}", level="error", auto_dismiss_ms=5000)


async def _run_platform_admin_correlation_copy(job_id: str, payload: dict[str, Any]) -> None:
    source = str(payload.get("source_profile") or "")
    target = str(payload.get("target_profile") or "")
    rule_names = [str(item) for item in (payload.get("rule_names") or [])]
    if not source or not target or not rule_names:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "platform_admin.correlation_copy", "error": "source_profile, target_profile, rule_names required"})
        return
    await broadcast({"type": "job.started", "job_id": job_id, "action": "platform_admin.correlation_copy", "payload": payload})

    def on_progress(event: dict[str, Any]) -> None:
        _publish_job_progress(job_id, "platform_admin.correlation_copy", event)
        maybe_publish_item_copied_from_progress(
            event,
            source=source,
            target=target,
            title="Correlation rules copy",
        )

    try:
        with LongOperationProgress(on_progress, action="platform_admin.correlation_copy") as progress:
            progress.set_current(source=source, target=target, section="correlation-rules", count=len(rule_names))
            result = await asyncio.to_thread(
                copy_correlation_rules_to_tenant,
                source,
                target,
                rule_names,
                overwrite=bool(payload.get("overwrite")),
                stop_on_conflict=bool(payload.get("stop_on_conflict")),
                name_suffix=payload.get("name_suffix"),
                on_progress=on_progress,
            )
        await broadcast({"type": "job.completed", "job_id": job_id, "action": "platform_admin.correlation_copy", "result": result})
        if not result.get("executed"):
            publish_notification(
                result.get("error") or "Correlation copy finished with issues",
                level="error",
                title="Correlation rules copy",
                auto_dismiss_ms=5000,
            )
    except Exception as exc:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "platform_admin.correlation_copy", "error": str(exc)})
        publish_notification(f"Correlation copy failed: {exc}", level="error", auto_dismiss_ms=5000)


async def _run_platform_admin_bioc_copy(job_id: str, payload: dict[str, Any]) -> None:
    source = str(payload.get("source_profile") or "")
    target = str(payload.get("target_profile") or "")
    names = [str(item) for item in (payload.get("names") or payload.get("bioc_names") or [])]
    if not source or not target or not names:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "platform_admin.bioc_copy", "error": "source_profile, target_profile, names required"})
        return
    await broadcast({"type": "job.started", "job_id": job_id, "action": "platform_admin.bioc_copy", "payload": payload})

    def on_progress(event: dict[str, Any]) -> None:
        _publish_job_progress(job_id, "platform_admin.bioc_copy", event)
        maybe_publish_item_copied_from_progress(
            event,
            source=source,
            target=target,
            title="BIOC copy",
        )

    try:
        with LongOperationProgress(on_progress, action="platform_admin.bioc_copy") as progress:
            progress.set_current(source=source, target=target, section="biocs", count=len(names))
            result = await asyncio.to_thread(
                copy_biocs_to_tenant,
                source,
                target,
                names,
                overwrite=bool(payload.get("overwrite")),
                stop_on_conflict=bool(payload.get("stop_on_conflict")),
                name_suffix=payload.get("name_suffix"),
                on_progress=on_progress,
            )
        await broadcast({"type": "job.completed", "job_id": job_id, "action": "platform_admin.bioc_copy", "result": result})
        if not result.get("executed"):
            publish_notification(
                result.get("error") or "BIOC copy finished with issues",
                level="error",
                title="BIOC copy",
                auto_dismiss_ms=5000,
            )
    except Exception as exc:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "platform_admin.bioc_copy", "error": str(exc)})
        publish_notification(f"BIOC copy failed: {exc}", level="error", auto_dismiss_ms=5000)


async def _run_platform_admin_indicator_copy(job_id: str, payload: dict[str, Any]) -> None:
    source = str(payload.get("source_profile") or "")
    target = str(payload.get("target_profile") or "")
    ids = [str(item) for item in (payload.get("ids") or [])]
    if not source or not target or not ids:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "platform_admin.indicator_copy", "error": "source_profile, target_profile, ids required"})
        return
    await broadcast({"type": "job.started", "job_id": job_id, "action": "platform_admin.indicator_copy", "payload": payload})

    def on_progress(event: dict[str, Any]) -> None:
        _publish_job_progress(job_id, "platform_admin.indicator_copy", event)
        maybe_publish_item_copied_from_progress(
            event,
            source=source,
            target=target,
            title="Indicator copy",
        )

    try:
        with LongOperationProgress(on_progress, action="platform_admin.indicator_copy") as progress:
            progress.set_current(source=source, target=target, section="indicators", count=len(ids))
            result = await asyncio.to_thread(
                copy_indicators_to_tenant,
                source,
                target,
                ids,
                overwrite=bool(payload.get("overwrite")),
                stop_on_conflict=bool(payload.get("stop_on_conflict")),
                on_progress=on_progress,
            )
        await broadcast({"type": "job.completed", "job_id": job_id, "action": "platform_admin.indicator_copy", "result": result})
        if not result.get("executed"):
            publish_notification(
                result.get("error") or "Indicator copy finished with issues",
                level="error",
                title="Indicator copy",
                auto_dismiss_ms=5000,
            )
    except Exception as exc:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "platform_admin.indicator_copy", "error": str(exc)})
        publish_notification(f"Indicator copy failed: {exc}", level="error", auto_dismiss_ms=5000)


async def _run_design_content_delete(job_id: str, payload: dict[str, Any]) -> None:
    profile = str(payload.get("profile") or "")
    asset = str(payload.get("asset") or "")
    item_ids = [str(item) for item in (payload.get("item_ids") or [])]
    if not profile or not asset or not item_ids:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "design_content.delete", "error": "profile, asset, item_ids required"})
        return
    await broadcast({"type": "job.started", "job_id": job_id, "action": "design_content.delete", "payload": payload})
    publish_notification(f"Deleting {asset} on {profile}…", level="info", auto_dismiss_ms=0)

    def on_progress(event: dict[str, Any]) -> None:
        _publish_job_progress(job_id, "design_content.delete", event)

    try:
        with LongOperationProgress(on_progress, action="design_content.delete") as progress:
            progress.set_current(profile=profile, asset=asset, item_count=len(item_ids))
            result = await asyncio.to_thread(delete_assets, profile, asset, item_ids)  # type: ignore[arg-type]
        await broadcast({"type": "job.completed", "job_id": job_id, "action": "design_content.delete", "result": result})
        publish_delete_success_notifications(
            result if isinstance(result, dict) else {},
            title=f"Delete {asset}",
            profile=profile,
            asset=asset,
        )
    except Exception as exc:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "design_content.delete", "error": str(exc)})
        publish_notification(f"Design content delete failed: {exc}", level="error")


async def _run_platform_admin_correlation_delete(job_id: str, payload: dict[str, Any]) -> None:
    profile = str(payload.get("profile") or "")
    names = [str(item) for item in (payload.get("names") or [])]
    if not profile or not names:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "platform_admin.correlation_delete", "error": "profile, names required"})
        return
    await broadcast({"type": "job.started", "job_id": job_id, "action": "platform_admin.correlation_delete", "payload": payload})
    publish_notification(f"Deleting correlation rules on {profile}…", level="info", auto_dismiss_ms=0)

    def on_progress(event: dict[str, Any]) -> None:
        _publish_job_progress(job_id, "platform_admin.correlation_delete", event)

    try:
        resolved = get_profile(profile)
        with LongOperationProgress(on_progress, action="platform_admin.correlation_delete") as progress:
            progress.set_current(profile=profile, item_count=len(names))
            results = await asyncio.to_thread(platform_admin_api.delete_correlation_rules, resolved, names)
            await asyncio.to_thread(refresh_platform_admin_section, profile, "correlation-rules")
        payload = {"profile": profile, "results": results}
        await broadcast({"type": "job.completed", "job_id": job_id, "action": "platform_admin.correlation_delete", "result": payload})
        publish_delete_success_notifications(payload, title="Correlation rules delete", profile=profile)
    except Exception as exc:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "platform_admin.correlation_delete", "error": str(exc)})
        publish_notification(f"Correlation rule delete failed: {exc}", level="error")


async def _run_platform_admin_bioc_delete(job_id: str, payload: dict[str, Any]) -> None:
    profile = str(payload.get("profile") or "")
    names = [str(item) for item in (payload.get("names") or [])]
    if not profile or not names:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "platform_admin.bioc_delete", "error": "profile, names required"})
        return
    await broadcast({"type": "job.started", "job_id": job_id, "action": "platform_admin.bioc_delete", "payload": payload})
    publish_notification(f"Deleting BIOCs on {profile}…", level="info", auto_dismiss_ms=0)

    def on_progress(event: dict[str, Any]) -> None:
        _publish_job_progress(job_id, "platform_admin.bioc_delete", event)

    try:
        resolved = get_profile(profile)
        with LongOperationProgress(on_progress, action="platform_admin.bioc_delete") as progress:
            progress.set_current(profile=profile, item_count=len(names))
            results = await asyncio.to_thread(platform_admin_api.delete_biocs, resolved, names)
            await asyncio.to_thread(refresh_platform_admin_section, profile, "biocs")
        payload = {"profile": profile, "results": results}
        await broadcast({"type": "job.completed", "job_id": job_id, "action": "platform_admin.bioc_delete", "result": payload})
        publish_delete_success_notifications(payload, title="BIOC delete", profile=profile)
    except Exception as exc:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "platform_admin.bioc_delete", "error": str(exc)})
        publish_notification(f"BIOC delete failed: {exc}", level="error")


async def _run_platform_admin_indicator_delete(job_id: str, payload: dict[str, Any]) -> None:
    profile = str(payload.get("profile") or "")
    ids = [str(item) for item in (payload.get("ids") or [])]
    if not profile or not ids:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "platform_admin.indicator_delete", "error": "profile, ids required"})
        return
    await broadcast({"type": "job.started", "job_id": job_id, "action": "platform_admin.indicator_delete", "payload": payload})
    publish_notification(f"Deleting indicators on {profile}…", level="info", auto_dismiss_ms=0)

    def on_progress(event: dict[str, Any]) -> None:
        _publish_job_progress(job_id, "platform_admin.indicator_delete", event)

    try:
        resolved = get_profile(profile)
        with LongOperationProgress(on_progress, action="platform_admin.indicator_delete") as progress:
            progress.set_current(profile=profile, item_count=len(ids))
            result, status = await asyncio.to_thread(platform_admin_api.delete_indicators, resolved, ids)
            await asyncio.to_thread(refresh_platform_admin_section, profile, "indicators")
        payload = {
            "profile": profile,
            "results": [{"id": indicator_id, "status": status} for indicator_id in ids],
            "status": status,
            "result": result,
        }
        await broadcast({
            "type": "job.completed",
            "job_id": job_id,
            "action": "platform_admin.indicator_delete",
            "result": payload,
        })
        publish_delete_success_notifications(payload, title="Indicator delete", profile=profile)
    except Exception as exc:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "platform_admin.indicator_delete", "error": str(exc)})
        publish_notification(f"Indicator delete failed: {exc}", level="error")


async def _run_platform_admin_refresh(job_id: str, payload: dict[str, Any]) -> None:
    profile = str(payload.get("profile") or "")
    section_raw = payload.get("section")
    if not profile:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "platform_admin.refresh", "error": "profile required"})
        return
    await broadcast({"type": "job.started", "job_id": job_id, "action": "platform_admin.refresh", "payload": payload})
    publish_notification(f"Refreshing platform admin data for {profile}…", level="info", auto_dismiss_ms=0)

    def on_progress(event: dict[str, Any]) -> None:
        _publish_job_progress(job_id, "platform_admin.refresh", event)

    try:
        with LongOperationProgress(on_progress, action="platform_admin.refresh") as progress:
            if section_raw:
                section = str(section_raw)
                if section not in ADMIN_SECTIONS:
                    raise ValueError(f"section must be one of: {', '.join(ADMIN_SECTIONS)}")
                progress.set_current(section=section, status="running")
                result = await asyncio.to_thread(refresh_platform_admin_section, profile, section)  # type: ignore[arg-type]
            else:
                progress.set_in_flight([{"section": section, "status": "pending"} for section in ADMIN_SECTIONS])
                result = await asyncio.to_thread(refresh_platform_admin_cache, profile)
            progress.set_current(status="completed")
        await broadcast({"type": "job.completed", "job_id": job_id, "action": "platform_admin.refresh", "result": result})
        publish_notification(f"Platform admin refresh complete for {profile}", level="success")
    except Exception as exc:
        await broadcast({"type": "job.failed", "job_id": job_id, "action": "platform_admin.refresh", "error": str(exc)})
        publish_notification(f"Platform admin refresh failed: {exc}", level="error")


async def _dispatch_job(message: dict[str, Any]) -> None:
    job_id = str(message.get("job_id") or uuid.uuid4().hex)
    action = str(message.get("action") or "")
    payload = message.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    if action == "cache.refresh":
        asyncio.create_task(_run_cache_refresh(job_id, payload))
        return

    if action == "playbooks.refactor.execute":
        asyncio.create_task(_run_refactor_execute(job_id, payload))
        return

    if action == "playbooks.refactor.workflow":
        asyncio.create_task(_run_refactor_workflow(job_id, payload))
        return

    if action == "design_content.refresh":
        asyncio.create_task(_run_design_content_refresh(job_id, payload))
        return

    if action == "design_content.copy":
        asyncio.create_task(_run_design_content_copy(job_id, payload))
        return

    if action == "design_content.orchestrate":
        asyncio.create_task(_run_design_content_orchestrate(job_id, payload))
        return

    if action == "design_content.delete":
        asyncio.create_task(_run_design_content_delete(job_id, payload))
        return

    if action == "platform_admin.refresh":
        asyncio.create_task(_run_platform_admin_refresh(job_id, payload))
        return

    if action == "platform_admin.correlation_copy":
        asyncio.create_task(_run_platform_admin_correlation_copy(job_id, payload))
        return

    if action == "platform_admin.bioc_copy":
        asyncio.create_task(_run_platform_admin_bioc_copy(job_id, payload))
        return

    if action == "platform_admin.indicator_copy":
        asyncio.create_task(_run_platform_admin_indicator_copy(job_id, payload))
        return

    if action == "platform_admin.correlation_delete":
        asyncio.create_task(_run_platform_admin_correlation_delete(job_id, payload))
        return

    if action == "platform_admin.bioc_delete":
        asyncio.create_task(_run_platform_admin_bioc_delete(job_id, payload))
        return

    if action == "platform_admin.indicator_delete":
        asyncio.create_task(_run_platform_admin_indicator_delete(job_id, payload))
        return

    await broadcast({
        "type": "job.failed",
        "job_id": job_id,
        "action": action,
        "error": f"Unknown job action: {action or '(empty)'}",
    })


async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    subscribe(websocket)
    await broadcast({
        "type": "connected",
        "message": "Cortex PS Toolkit WebSocket connected",
    })
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = __import__("json").loads(raw)
            except Exception:
                await websocket.send_json({"type": "error", "error": "Invalid JSON message"})
                continue
            if not isinstance(message, dict):
                await websocket.send_json({"type": "error", "error": "Message must be a JSON object"})
                continue
            msg_type = str(message.get("type") or "")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if msg_type == "job":
                await _dispatch_job(message)
                continue
            await websocket.send_json({"type": "error", "error": f"Unknown message type: {msg_type}"})
    except WebSocketDisconnect:
        pass
    finally:
        unsubscribe(websocket)
