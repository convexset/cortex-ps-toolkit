"""REST handlers for saved Object Setup bundles (per source tenant)."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..design_content.bundle_presets import (
    delete_bundle_preset,
    get_bundle_preset,
    list_bundle_presets,
    resolve_bundle_items,
    save_bundle_preset,
)
from .common import error_response, read_json, run_sync


def _source_profile_from_request(request: Request, body: dict | None = None) -> str:
    raw = request.query_params.get("profile") or request.query_params.get("source_profile")
    if not raw and body:
        raw = body.get("source_profile") or body.get("profile")
    return str(raw or "").strip()


async def api_object_setup_bundles_list(request: Request) -> JSONResponse:
    try:
        source_profile = _source_profile_from_request(request)
        if not source_profile:
            return JSONResponse({"error": "profile query parameter required"}, status_code=400)
        bundles = await run_sync(list_bundle_presets, source_profile=source_profile)
        return JSONResponse({"profile": source_profile, "bundles": bundles})
    except ValueError as exc:
        return error_response(exc, 400)


async def api_object_setup_bundles_save(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        source_profile = _source_profile_from_request(request, body)
        if not source_profile:
            return JSONResponse({"error": "source_profile required"}, status_code=400)
        entry = await run_sync(
            save_bundle_preset,
            name=str(body.get("name") or body.get("id") or ""),
            source_profile=source_profile,
            items=body.get("items") or [],
            bundle_id=body.get("id"),
        )
        return JSONResponse(entry)
    except (KeyError, ValueError) as exc:
        return error_response(exc, 400)


async def api_object_setup_bundles_get(request: Request) -> JSONResponse:
    bundle_id = request.path_params["bundle_id"]
    source_profile = _source_profile_from_request(request)
    if not source_profile:
        return JSONResponse({"error": "profile query parameter required"}, status_code=400)
    try:
        entry = await run_sync(get_bundle_preset, source_profile, bundle_id)
        return JSONResponse(entry)
    except KeyError as exc:
        return error_response(exc, 404)


async def api_object_setup_bundles_delete(request: Request) -> JSONResponse:
    bundle_id = request.path_params["bundle_id"]
    source_profile = _source_profile_from_request(request)
    if not source_profile:
        return JSONResponse({"error": "profile query parameter required"}, status_code=400)
    deleted = await run_sync(delete_bundle_preset, source_profile, bundle_id)
    if not deleted:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"deleted": True, "id": bundle_id, "profile": source_profile})


async def api_object_setup_bundles_resolve(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or body.get("source_profile") or "")
        items = body.get("items") or []
        if not profile:
            raise ValueError("profile required")
        result = await run_sync(resolve_bundle_items, profile, items)
        return JSONResponse(result)
    except (KeyError, ValueError) as exc:
        status = 404 if isinstance(exc, KeyError) else 400
        return error_response(exc, status)
