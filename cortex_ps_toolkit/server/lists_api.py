"""HTTP handlers for list detail."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..core.client import TenantApiError
from ..lists.detail import get_list_detail
from ..platforms import UnsupportedOperation
from .common import error_response, run_sync


async def api_list_detail(request: Request) -> JSONResponse:
    profile = request.query_params.get("profile", "")
    if not profile:
        return JSONResponse({"error": "profile query parameter required"}, status_code=400)
    list_id = request.path_params["list_id"]
    try:
        payload = await run_sync(get_list_detail, profile, list_id)
        return JSONResponse(payload)
    except KeyError as exc:
        return error_response(exc, 404)
    except (TenantApiError, UnsupportedOperation, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)
