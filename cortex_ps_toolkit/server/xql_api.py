"""XQL preset and visualisation HTTP handlers."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..xql.presets import delete_user_preset, list_builtin_presets, list_user_presets, save_user_preset
from ..xql.schema import infer_schema
from ..xql.visualizations import VisualSpec, chart_types_for_api, render_plotly_figure, validate_visual_spec
from ..xql.visualizations.storage import delete_visualization, list_saved_visualizations, save_visualization
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


async def api_xql_visualization_chart_types(_request: Request) -> JSONResponse:
    return JSONResponse({"chart_types": await run_sync(chart_types_for_api)})


async def api_xql_visualization_validate(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        rows = body.get("rows") or []
        if not isinstance(rows, list):
            return JSONResponse({"error": "rows must be an array"}, status_code=400)
        spec = VisualSpec.from_dict(body.get("spec") or {})
        result = await run_sync(validate_visual_spec, rows, spec)
        return JSONResponse(result.to_dict())
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_xql_visualization_render(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        rows = body.get("rows") or []
        if not isinstance(rows, list):
            return JSONResponse({"error": "rows must be an array"}, status_code=400)
        spec = VisualSpec.from_dict(body.get("spec") or {})
        figure = await run_sync(render_plotly_figure, rows, spec)
        validation = await run_sync(validate_visual_spec, rows, spec)
        return JSONResponse({
            "figure": figure,
            "validation": validation.to_dict(),
        })
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_xql_visualization_schema(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        rows = body.get("rows") or []
        if not isinstance(rows, list):
            return JSONResponse({"error": "rows must be an array"}, status_code=400)
        schema = await run_sync(infer_schema, rows)
        return JSONResponse({"schema": schema})
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_xql_visualizations_list(request: Request) -> JSONResponse:
    profile = request.query_params.get("profile")
    items = await run_sync(list_saved_visualizations, profile=profile)
    return JSONResponse({"visualizations": items})


async def api_xql_visualizations_save(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "").strip()
        label = str(body.get("label") or "").strip()
        if not profile:
            return JSONResponse({"error": "profile required"}, status_code=400)
        spec = VisualSpec.from_dict(body.get("spec") or {})
        saved = await run_sync(
            save_visualization,
            spec=spec,
            label=label or spec.label or spec.title or "Chart",
            profile=profile,
            visualization_id=body.get("id"),
            query_id=body.get("query_id"),
            columns_fingerprint=body.get("columns_fingerprint"),
        )
        return JSONResponse(saved)
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_xql_visualizations_delete(request: Request, visualization_id: str) -> JSONResponse:
    deleted = await run_sync(delete_visualization, visualization_id)
    if not deleted:
        return JSONResponse({"error": "visualization not found"}, status_code=404)
    return JSONResponse({"ok": True, "id": visualization_id})
