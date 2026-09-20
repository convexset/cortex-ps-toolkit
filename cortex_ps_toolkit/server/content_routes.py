"""Shared HTTP handlers for cached content resources (playbooks, scripts)."""

from __future__ import annotations

from typing import Any, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..cache.status import cache_scope_status
from ..core.client import TenantApiError
from ..credentials import get_profile
from ..platforms import UnsupportedOperation
from ..settings import cache_ttl_seconds
from .common import error_response, read_json, run_sync
from .copy_notifications import publish_copy_success_notifications
from .delete_notifications import publish_delete_success_notifications


def make_list_handler(
    *,
    list_cached: Callable[[str], list[dict[str, Any]]],
    load_index: Callable[[Any], dict[str, Any]],
    items_key: str,
) -> Callable[[Request], JSONResponse]:
    async def handler(request: Request) -> JSONResponse:
        profile = request.query_params.get("profile", "")
        if not profile:
            return JSONResponse({"error": "profile query parameter required"}, status_code=400)
        try:
            resolved = await run_sync(get_profile, profile)
            items = await run_sync(list_cached, profile)
            cache_meta: dict = {}
            try:
                index = await run_sync(load_index, resolved)
                cache_meta = cache_scope_status(index)
            except Exception:
                cache_meta = {}
            return JSONResponse({
                "profile": profile,
                "refreshed_at": cache_meta.get("refreshed_at"),
                "cache": cache_meta,
                "ttl_seconds": cache_ttl_seconds(),
                items_key: items,
                "count": len(items),
            })
        except KeyError as exc:
            return error_response(exc, 404)

    return handler


def make_refresh_handler(refresh_cache: Callable[[str], dict[str, Any]]) -> Callable[[Request], JSONResponse]:
    async def handler(request: Request) -> JSONResponse:
        try:
            body = await read_json(request)
            profile = str(body.get("profile") or "")
            if not profile:
                return JSONResponse({"error": "profile required"}, status_code=400)
            result = await run_sync(refresh_cache, profile)
            return JSONResponse(result)
        except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
            status = 502 if isinstance(exc, TenantApiError) else 400 if isinstance(exc, UnsupportedOperation) else 404
            return error_response(exc, status)

    return handler


def make_copy_preview_handler(
    plan_copy: Callable[..., dict[str, Any]],
    *,
    ids_key: str,
) -> Callable[[Request], JSONResponse]:
    async def handler(request: Request) -> JSONResponse:
        try:
            body = await read_json(request)
            source = str(body.get("source_profile") or "")
            target = str(body.get("target_profile") or "")
            item_ids = [str(item) for item in (body.get(ids_key) or [])]
            overwrite = bool(body.get("overwrite"))
            stop_on_conflict = bool(body.get("stop_on_conflict"))
            if stop_on_conflict and overwrite:
                raise ValueError("overwrite and stop_on_conflict cannot both be enabled")
            if not source or not target or not item_ids:
                raise ValueError(f"source_profile, target_profile, {ids_key} required")
            plan = await run_sync(
                plan_copy,
                source,
                target,
                item_ids,
                overwrite=overwrite,
                stop_on_conflict=stop_on_conflict,
            )
            return JSONResponse(plan)
        except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
            status = 502 if isinstance(exc, TenantApiError) else 400 if isinstance(exc, UnsupportedOperation) else 404
            return error_response(exc, status)

    return handler


def make_copy_handler(
    copy_to_tenant: Callable[..., dict[str, Any]],
    *,
    ids_key: str,
    copy_title: str = "Copy",
) -> Callable[[Request], JSONResponse]:
    async def handler(request: Request) -> JSONResponse:
        try:
            body = await read_json(request)
            source = str(body.get("source_profile") or "")
            target = str(body.get("target_profile") or "")
            item_ids = [str(item) for item in (body.get(ids_key) or [])]
            overwrite = bool(body.get("overwrite"))
            stop_on_conflict = bool(body.get("stop_on_conflict"))
            if stop_on_conflict and overwrite:
                raise ValueError("overwrite and stop_on_conflict cannot both be enabled")
            if not source or not target or not item_ids:
                raise ValueError(f"source_profile, target_profile, {ids_key} required")
            result = await run_sync(
                copy_to_tenant,
                source,
                target,
                item_ids,
                overwrite=overwrite,
                stop_on_conflict=stop_on_conflict,
            )
            if not result.get("aborted"):
                publish_copy_success_notifications(
                    result,
                    title=copy_title,
                    source=source,
                    target=target,
                )
            return JSONResponse(result)
        except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
            status = 502 if isinstance(exc, TenantApiError) else 400 if isinstance(exc, UnsupportedOperation) else 404
            return error_response(exc, status)

    return handler


def make_delete_preview_handler(
    plan_delete: Callable[[str, list[str]], dict[str, Any]],
    *,
    ids_key: str,
) -> Callable[[Request], JSONResponse]:
    async def handler(request: Request) -> JSONResponse:
        try:
            body = await read_json(request)
            profile = str(body.get("profile") or "")
            item_ids = [str(item) for item in (body.get(ids_key) or [])]
            if not profile or not item_ids:
                raise ValueError(f"profile and {ids_key} required")
            plan = await run_sync(plan_delete, profile, item_ids)
            return JSONResponse(plan)
        except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
            status = 502 if isinstance(exc, TenantApiError) else 400 if isinstance(exc, UnsupportedOperation) else 404
            return error_response(exc, status)

    return handler


def make_delete_handler(
    delete_items: Callable[[str, list[str]], dict[str, Any]],
    *,
    ids_key: str,
    delete_title: str = "Delete",
) -> Callable[[Request], JSONResponse]:
    async def handler(request: Request) -> JSONResponse:
        try:
            body = await read_json(request)
            profile = str(body.get("profile") or "")
            item_ids = [str(item) for item in (body.get(ids_key) or [])]
            if not profile or not item_ids:
                raise ValueError(f"profile and {ids_key} required")
            result = await run_sync(delete_items, profile, item_ids)
            publish_delete_success_notifications(result, title=delete_title, profile=profile)
            return JSONResponse(result)
        except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
            status = 502 if isinstance(exc, TenantApiError) else 400 if isinstance(exc, UnsupportedOperation) else 404
            return error_response(exc, status)

    return handler
