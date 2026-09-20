"""Cache status and toolkit settings HTTP handlers."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..cache.status import cache_status_for_profile
from ..settings import load_settings, save_settings
from .common import read_json, run_sync


async def api_cache_status(request: Request) -> JSONResponse:
    profile = request.query_params.get("profile", "")
    if not profile:
        return JSONResponse({"error": "profile query parameter required"}, status_code=400)
    try:
        status = await run_sync(cache_status_for_profile, profile)
        return JSONResponse(status)
    except KeyError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)


async def api_settings_get(_request: Request) -> JSONResponse:
    return JSONResponse(load_settings())


async def api_settings_patch(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        if not isinstance(body, dict):
            return JSONResponse({"error": "JSON object required"}, status_code=400)
        allowed: dict[str, Any] = {}
        for key in ("cache_ttl_seconds", "max_inflight_per_host", "max_inflight_global", "refactor_execution_mode"):
            if key in body:
                allowed[key] = body[key]
        if not allowed:
            return JSONResponse({"error": "No supported settings in body"}, status_code=400)
        merged = load_settings()
        merged.update(allowed)
        saved = await run_sync(save_settings, merged)
        return JSONResponse(saved)
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
