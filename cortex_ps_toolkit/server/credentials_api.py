"""REST handlers for credential management."""

from __future__ import annotations

import json

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..credentials import (
    create_profile_from_input,
    get_profile,
    import_lab_profiles,
    list_profiles,
    parse_expiry,
    purge_expired_profiles,
    remove_profile,
    set_profile_expiry,
    set_profile_verify_ssl,
    update_profile_from_input,
)
from ..credentials_validate import validate_profile
from ..paths import package_root
from .common import error_response, read_json, run_sync


async def api_credentials_list(_request: Request) -> JSONResponse:
    def _load() -> list:
        purge_expired_profiles()
        return list_profiles()

    profiles = await run_sync(_load)
    return JSONResponse({"profiles": [profile.to_public_dict() for profile in profiles]})


async def api_credentials_get(request: Request) -> JSONResponse:
    slug = request.path_params["slug"]
    try:
        profile = await run_sync(get_profile, slug)
        return JSONResponse(profile.to_public_dict())
    except KeyError as exc:
        return error_response(exc, 404)


async def api_credentials_create(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = await run_sync(create_profile_from_input, body)
        return JSONResponse(profile.to_public_dict(), status_code=201)
    except (ValueError, KeyError) as exc:
        return error_response(exc, 400)


async def api_credentials_update(request: Request) -> JSONResponse:
    try:
        slug = request.path_params["slug"]
        body = await read_json(request)
        profile = await run_sync(update_profile_from_input, slug, body)
        return JSONResponse(profile.to_public_dict())
    except KeyError as exc:
        return error_response(exc, 404)
    except ValueError as exc:
        return error_response(exc, 400)


async def api_credentials_delete(request: Request) -> JSONResponse:
    try:
        slug = request.path_params["slug"]
        removed = await run_sync(remove_profile, slug)
        return JSONResponse({"deleted": removed.slug, "id": removed.id})
    except KeyError as exc:
        return error_response(exc, 404)


async def api_credentials_import_lab(_request: Request) -> JSONResponse:
    def _import() -> list:
        manifest = package_root() / "presets" / "credentials" / "lab-sources.json"
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        sources = payload.get("sources") or []
        purge_expired_profiles()
        return import_lab_profiles(sources, base_dir=manifest.parent)

    imported = await run_sync(_import)
    return JSONResponse({
        "imported": len(imported),
        "profiles": [profile.to_public_dict() for profile in imported],
    })


async def api_credentials_purge_expired(request: Request) -> JSONResponse:
    body = await read_json(request)
    dry_run = bool(body.get("dry_run"))
    removed = await run_sync(purge_expired_profiles, dry_run=dry_run)
    return JSONResponse({
        "dry_run": dry_run,
        "purged": [profile.slug for profile in removed],
    })


async def api_credentials_validate(request: Request) -> JSONResponse:
    slug = request.path_params["slug"]
    try:
        result = await run_sync(validate_profile, slug)
        return JSONResponse(result)
    except KeyError as exc:
        return error_response(exc, 404)


async def api_credentials_expiry(request: Request) -> JSONResponse:
    slug = request.path_params["slug"]
    try:
        body = await read_json(request)
        expires_raw = body.get("expires_at") if "expires_at" in body else body.get("expires")
        expires_at = parse_expiry(str(expires_raw)) if expires_raw else None
        profile = await run_sync(set_profile_expiry, slug, expires_at)
        return JSONResponse(profile.to_public_dict())
    except KeyError as exc:
        return error_response(exc, 404)
    except ValueError as exc:
        return error_response(exc, 400)


async def api_credentials_verify_ssl(request: Request) -> JSONResponse:
    slug = request.path_params["slug"]
    try:
        body = await read_json(request)
        if "verify_ssl" not in body:
            return JSONResponse({"error": "verify_ssl required"}, status_code=400)
        profile = await run_sync(set_profile_verify_ssl, slug, bool(body.get("verify_ssl")))
        return JSONResponse(profile.to_public_dict())
    except KeyError as exc:
        return error_response(exc, 404)
