"""REST handlers for design-time content assets."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..core.client import TenantApiError
from ..credentials import get_profile
from ..design_content import api as design_api
from ..design_content.copy import copy_assets_to_tenant, plan_asset_copy
from ..design_content.delete import delete_assets, plan_asset_delete
from ..design_content.cache import load_index
from ..design_content.orchestrator import execute_cross_tenant_workflow
from ..design_content.service import get_item_body, list_cached_items, refresh_all_cache, refresh_asset_cache
from ..design_content.types import ASSET_KINDS, AssetKind
from ..platforms import UnsupportedOperation
from .common import error_response, read_json, run_sync
from .copy_notifications import (
    maybe_publish_item_copied_from_progress,
    publish_object_bundle_complete_notification,
)
from .delete_notifications import publish_delete_success_notifications


def _parse_asset(raw: str) -> AssetKind:
    asset = raw.strip().lower()
    if asset not in ASSET_KINDS:
        raise ValueError(f"asset must be one of: {', '.join(ASSET_KINDS)}")
    return asset  # type: ignore[return-value]


async def api_design_content_list(request: Request) -> JSONResponse:
    asset = _parse_asset(request.path_params["asset"])
    profile = request.query_params.get("profile", "")
    if not profile:
        return JSONResponse({"error": "profile query parameter required"}, status_code=400)
    try:
        resolved = get_profile(profile)
        items = await run_sync(list_cached_items, profile, asset)
        index = load_index(resolved, asset)
        return JSONResponse({
            "profile": profile,
            "asset": asset,
            "items": items,
            "count": len(items),
            "refreshed_at": index.get("refreshed_at"),
        })
    except (KeyError, ValueError, UnsupportedOperation) as exc:
        status = 404 if isinstance(exc, KeyError) else 400
        return error_response(exc, status)


async def api_design_content_get_one(request: Request) -> JSONResponse:
    asset = _parse_asset(request.path_params["asset"])
    item_id = request.path_params["item_id"]
    profile = request.query_params.get("profile", "")
    if not profile:
        return JSONResponse({"error": "profile query parameter required"}, status_code=400)
    try:
        body = await run_sync(get_item_body, profile, asset, item_id)
        return JSONResponse({"profile": profile, "asset": asset, "item_id": item_id, "body": body})
    except (KeyError, TenantApiError, UnsupportedOperation) as exc:
        status = 404 if isinstance(exc, KeyError) else 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_design_content_refresh(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        asset_raw = body.get("asset")
        if not profile:
            return JSONResponse({"error": "profile required"}, status_code=400)
        if asset_raw:
            asset = _parse_asset(str(asset_raw))
            result = await run_sync(refresh_asset_cache, profile, asset)
        else:
            result = await run_sync(refresh_all_cache, profile)
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


def _parse_copy_body(body: dict[str, Any], asset: AssetKind) -> tuple[str, str, list[str], bool, bool, str | None]:
    source = str(body.get("source_profile") or "")
    target = str(body.get("target_profile") or "")
    item_ids = [str(item) for item in (body.get("item_ids") or [])]
    overwrite = bool(body.get("overwrite"))
    stop_on_conflict = bool(body.get("stop_on_conflict"))
    name_suffix = body.get("name_suffix")
    if stop_on_conflict and overwrite:
        raise ValueError("overwrite and stop_on_conflict cannot both be enabled")
    if not source or not target or not item_ids:
        raise ValueError("source_profile, target_profile, item_ids required")
    return source, target, item_ids, overwrite, stop_on_conflict, str(name_suffix) if name_suffix else None


async def api_design_content_copy_preview(request: Request) -> JSONResponse:
    asset = _parse_asset(request.path_params["asset"])
    try:
        body = await read_json(request)
        source, target, item_ids, overwrite, stop_on_conflict, name_suffix = _parse_copy_body(body, asset)
        plan = await run_sync(
            plan_asset_copy,
            source,
            target,
            asset,
            item_ids,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
            name_suffix=name_suffix,
        )
        return JSONResponse(plan)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_design_content_copy(request: Request) -> JSONResponse:
    asset = _parse_asset(request.path_params["asset"])
    try:
        body = await read_json(request)
        source, target, item_ids, overwrite, stop_on_conflict, name_suffix = _parse_copy_body(body, asset)
        prefer_direct = bool(body.get("prefer_direct_on_xsoar6", True))
        result = await run_sync(
            copy_assets_to_tenant,
            source,
            target,
            asset,
            item_ids,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
            name_suffix=name_suffix,
            prefer_direct_on_xsoar6=prefer_direct,
        )
        if result.get("executed"):
            publish_copy_success_notifications(
                result,
                title=f"Copy {asset}",
                source=source,
                target=target,
            )
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_design_content_delete_preview(request: Request) -> JSONResponse:
    asset = _parse_asset(request.path_params["asset"])
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        item_ids = [str(item) for item in (body.get("item_ids") or [])]
        if not profile or not item_ids:
            raise ValueError("profile and item_ids required")
        plan = await run_sync(plan_asset_delete, profile, asset, item_ids)
        return JSONResponse(plan)
    except (UnsupportedOperation, KeyError, ValueError) as exc:
        return error_response(exc, 400)


async def api_design_content_delete(request: Request) -> JSONResponse:
    asset = _parse_asset(request.path_params["asset"])
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        item_ids = [str(item) for item in (body.get("item_ids") or [])]
        if not profile or not item_ids:
            raise ValueError("profile and item_ids required")
        result = await run_sync(delete_assets, profile, asset, item_ids)
        publish_delete_success_notifications(
            result,
            title=f"Delete {asset}",
            profile=profile,
            asset=asset,
        )
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError, design_api.UnsupportedDelete) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_design_content_orchestrate(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        source = str(body.get("source_profile") or "")
        target = str(body.get("target_profile") or "")
        selections = body.get("selections") or {}
        if not source or not target or not isinstance(selections, dict):
            raise ValueError("source_profile, target_profile, selections required")
        def on_progress(event: dict[str, Any]) -> None:
            maybe_publish_item_copied_from_progress(
                event,
                source=source,
                target=target,
                title="Object Bundle copy",
            )

        result = await run_sync(
            execute_cross_tenant_workflow,
            source,
            target,
            {str(k): [str(item) for item in v] for k, v in selections.items()},
            overwrite=bool(body.get("overwrite")),
            stop_on_conflict=bool(body.get("stop_on_conflict")),
            name_suffix=body.get("name_suffix"),
            prefer_direct_on_xsoar6=bool(body.get("prefer_direct_on_xsoar6", True)),
            include_correlation_rules=bool(body.get("include_correlation_rules")),
            correlation_rule_names=[str(item) for item in (body.get("correlation_rule_names") or [])],
            on_progress=on_progress,
        )
        if result.get("executed"):
            publish_object_bundle_complete_notification(
                result,
                source=source,
                target=target,
            )
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)
