"""HTTP handlers for integration caches."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..core.client import TenantApiError
from ..credentials import get_profile
from ..integrations.cache import load_scope_cache
from ..integrations.detail import (
    get_integration_commands_detail,
    get_integration_definition_detail,
    get_integration_instance_detail,
)
from ..integrations.service import (
    list_cached_installed_packs,
    list_cached_integration_commands,
    list_cached_integration_instances,
    list_cached_tenant_credentials,
    refresh_integrations_cache,
)
from ..platforms import UnsupportedOperation
from .common import error_response, read_json, run_sync


async def api_integrations_configurations(request: Request) -> JSONResponse:
    profile = request.query_params.get("profile", "")
    if not profile:
        return JSONResponse({"error": "profile query parameter required"}, status_code=400)
    try:
        payload = await run_sync(list_cached_integration_instances, profile)
        configurations = payload.get("configurations") or []
        return JSONResponse({
            "profile": profile,
            "refreshed_at": payload.get("refreshed_at"),
            "configurations": configurations,
            "count": len(configurations),
        })
    except KeyError as exc:
        return error_response(exc, 404)


async def api_integrations_commands(request: Request) -> JSONResponse:
    profile = request.query_params.get("profile", "")
    if not profile:
        return JSONResponse({"error": "profile query parameter required"}, status_code=400)
    try:
        resolved = await run_sync(get_profile, profile)
        items = await run_sync(list_cached_integration_commands, profile)
        cache_meta = await run_sync(load_scope_cache, resolved, "commands")
        return JSONResponse({
            "profile": profile,
            "refreshed_at": cache_meta.get("refreshed_at"),
            "integrations": items,
            "count": len(items),
        })
    except KeyError as exc:
        return error_response(exc, 404)


async def api_integrations_instances(request: Request) -> JSONResponse:
    profile = request.query_params.get("profile", "")
    if not profile:
        return JSONResponse({"error": "profile query parameter required"}, status_code=400)
    try:
        payload = await run_sync(list_cached_integration_instances, profile)
        return JSONResponse({"profile": profile, **payload})
    except KeyError as exc:
        return error_response(exc, 404)


async def api_integrations_tenant_credentials(request: Request) -> JSONResponse:
    profile = request.query_params.get("profile", "")
    if not profile:
        return JSONResponse({"error": "profile query parameter required"}, status_code=400)
    try:
        items = await run_sync(list_cached_tenant_credentials, profile)
        cache_meta = await run_sync(load_scope_cache, profile, "tenant_credentials")
        return JSONResponse({
            "profile": profile,
            "refreshed_at": cache_meta.get("refreshed_at"),
            "credentials": items,
            "count": len(items),
        })
    except KeyError as exc:
        return error_response(exc, 404)


async def api_integrations_packs(request: Request) -> JSONResponse:
    profile = request.query_params.get("profile", "")
    if not profile:
        return JSONResponse({"error": "profile query parameter required"}, status_code=400)
    try:
        items = await run_sync(list_cached_installed_packs, profile)
        cache_meta = await run_sync(load_scope_cache, profile, "contentpacks")
        return JSONResponse({
            "profile": profile,
            "refreshed_at": cache_meta.get("refreshed_at"),
            "packs": items,
            "count": len(items),
        })
    except KeyError as exc:
        return error_response(exc, 404)


async def api_integrations_commands_detail(request: Request) -> JSONResponse:
    profile = request.query_params.get("profile", "")
    if not profile:
        return JSONResponse({"error": "profile query parameter required"}, status_code=400)
    integration_id = request.path_params["integration_id"]
    try:
        payload = await run_sync(get_integration_commands_detail, profile, integration_id)
        return JSONResponse(payload)
    except KeyError as exc:
        return error_response(exc, 404)
    except (TenantApiError, UnsupportedOperation, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_integrations_definition_detail(request: Request) -> JSONResponse:
    profile = request.query_params.get("profile", "")
    if not profile:
        return JSONResponse({"error": "profile query parameter required"}, status_code=400)
    integration_id = request.path_params["integration_id"]
    try:
        payload = await run_sync(get_integration_definition_detail, profile, integration_id)
        return JSONResponse(payload)
    except KeyError as exc:
        return error_response(exc, 404)
    except (TenantApiError, UnsupportedOperation, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_integrations_instance_detail(request: Request) -> JSONResponse:
    profile = request.query_params.get("profile", "")
    if not profile:
        return JSONResponse({"error": "profile query parameter required"}, status_code=400)
    instance_id = request.path_params["instance_id"]
    try:
        payload = await run_sync(get_integration_instance_detail, profile, instance_id)
        return JSONResponse(payload)
    except KeyError as exc:
        return error_response(exc, 404)
    except (TenantApiError, UnsupportedOperation, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_integrations_refresh(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        if not profile:
            return JSONResponse({"error": "profile required"}, status_code=400)
        result = await run_sync(refresh_integrations_cache, profile)
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)
