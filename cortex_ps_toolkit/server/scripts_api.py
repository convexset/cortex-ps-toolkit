"""HTTP handlers for automation script detail."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..core.client import TenantApiError
from ..scripts.detail import get_script_detail
from .common import error_response, run_sync


async def api_script_detail(request: Request) -> JSONResponse:
    profile = request.query_params.get("profile", "")
    if not profile:
        return JSONResponse({"error": "profile query parameter required"}, status_code=400)
    script_id = request.path_params["script_id"]
    try:
        payload = await run_sync(get_script_detail, profile, script_id)
        return JSONResponse(payload)
    except KeyError as exc:
        return error_response(exc, 404)
    except (TenantApiError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)
