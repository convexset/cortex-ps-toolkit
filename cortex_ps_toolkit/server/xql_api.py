"""XQL preset HTTP handlers."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..xql.presets import delete_user_preset, list_builtin_presets, list_user_presets, save_user_preset
from .common import read_json, run_sync


async def api_xql_builtin_presets(_request: Request) -> JSONResponse:
    return JSONResponse({"presets": await run_sync(list_builtin_presets)})


async def api_xql_user_presets(_request: Request) -> JSONResponse:
    return JSONResponse({"presets": await run_sync(list_user_presets)})


async def api_xql_user_presets_save(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        name = str(body.get("name") or "").strip()
        query = str(body.get("query") or "")
        if not name or not query.strip():
            return JSONResponse({"error": "name and query required"}, status_code=400)
        saved = await run_sync(
            save_user_preset,
            name=name,
            query=query,
            timeframe_ms=body.get("timeframe_ms") or body.get("timeframe"),
            query_name=body.get("query_name"),
            preset_id=body.get("id"),
        )
        return JSONResponse(saved)
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_xql_user_presets_delete(request: Request, preset_id: str) -> JSONResponse:
    deleted = await run_sync(delete_user_preset, preset_id)
    if not deleted:
        return JSONResponse({"error": "preset not found"}, status_code=404)
    return JSONResponse({"ok": True, "id": preset_id})
