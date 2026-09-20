"""REST handlers for platform administration sections."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..core.client import TenantApiError
from ..credentials import get_profile
from ..platform_admin import api as admin_api
from ..platform_admin.cache import load_index
from ..platform_admin.bioc_copy import copy_biocs_to_tenant
from ..platform_admin.copy import copy_correlation_rules_to_tenant
from ..platform_admin.indicator_copy import copy_indicators_to_tenant
from ..platform_admin.plan import (
    plan_bioc_copy,
    plan_bioc_delete,
    plan_correlation_copy,
    plan_correlation_delete,
    plan_indicator_copy,
)
from ..platform_admin.service import list_cached_items, refresh_all_cache, refresh_section_cache
from ..platform_admin.types import ADMIN_SECTIONS, AdminSection
from ..platforms import UnsupportedOperation
from .common import error_response, read_json, run_sync
from .copy_notifications import publish_copy_success_notifications
from .delete_notifications import publish_delete_success_notifications


def _parse_section(raw: str) -> AdminSection:
    section = raw.strip().lower()
    if section not in ADMIN_SECTIONS:
        raise ValueError(f"section must be one of: {', '.join(ADMIN_SECTIONS)}")
    return section  # type: ignore[return-value]


async def api_platform_admin_list(request: Request) -> JSONResponse:
    section = _parse_section(request.path_params["section"])
    profile = request.query_params.get("profile", "")
    if not profile:
        return JSONResponse({"error": "profile query parameter required"}, status_code=400)
    try:
        resolved = get_profile(profile)
        items = await run_sync(list_cached_items, profile, section)
        index = load_index(resolved, section)
        return JSONResponse({
            "profile": profile,
            "section": section,
            "items": items,
            "count": len(items),
            "refreshed_at": index.get("refreshed_at"),
        })
    except (KeyError, ValueError, UnsupportedOperation) as exc:
        status = 404 if isinstance(exc, KeyError) else 400
        return error_response(exc, status)


async def api_platform_admin_refresh(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        section_raw = body.get("section")
        if not profile:
            return JSONResponse({"error": "profile required"}, status_code=400)
        if section_raw:
            section = _parse_section(str(section_raw))
            result = await run_sync(refresh_section_cache, profile, section)
        else:
            result = await run_sync(refresh_all_cache, profile)
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_platform_admin_correlation_copy_preview(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        source = str(body.get("source_profile") or "")
        target = str(body.get("target_profile") or "")
        rule_names = [str(item) for item in (body.get("rule_names") or [])]
        if not source or not target or not rule_names:
            raise ValueError("source_profile, target_profile, rule_names required")
        result = await run_sync(
            plan_correlation_copy,
            source,
            target,
            rule_names,
            overwrite=bool(body.get("overwrite")),
            stop_on_conflict=bool(body.get("stop_on_conflict")),
            name_suffix=body.get("name_suffix"),
        )
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_platform_admin_correlation_copy(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        source = str(body.get("source_profile") or "")
        target = str(body.get("target_profile") or "")
        rule_names = [str(item) for item in (body.get("rule_names") or [])]
        if not source or not target or not rule_names:
            raise ValueError("source_profile, target_profile, rule_names required")
        result = await run_sync(
            copy_correlation_rules_to_tenant,
            source,
            target,
            rule_names,
            overwrite=bool(body.get("overwrite")),
            stop_on_conflict=bool(body.get("stop_on_conflict")),
            name_suffix=body.get("name_suffix"),
        )
        if result.get("executed"):
            publish_copy_success_notifications(
                result,
                title="Correlation rules copy",
                source=source,
                target=target,
            )
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_platform_admin_biocs_copy_preview(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        source = str(body.get("source_profile") or "")
        target = str(body.get("target_profile") or "")
        names = [str(item) for item in (body.get("names") or body.get("bioc_names") or [])]
        if not source or not target or not names:
            raise ValueError("source_profile, target_profile, names required")
        result = await run_sync(
            plan_bioc_copy,
            source,
            target,
            names,
            overwrite=bool(body.get("overwrite")),
            stop_on_conflict=bool(body.get("stop_on_conflict")),
            name_suffix=body.get("name_suffix"),
        )
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_platform_admin_biocs_copy(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        source = str(body.get("source_profile") or "")
        target = str(body.get("target_profile") or "")
        names = [str(item) for item in (body.get("names") or body.get("bioc_names") or [])]
        if not source or not target or not names:
            raise ValueError("source_profile, target_profile, names required")
        result = await run_sync(
            copy_biocs_to_tenant,
            source,
            target,
            names,
            overwrite=bool(body.get("overwrite")),
            stop_on_conflict=bool(body.get("stop_on_conflict")),
            name_suffix=body.get("name_suffix"),
        )
        if result.get("executed"):
            publish_copy_success_notifications(
                result,
                title="BIOC copy",
                source=source,
                target=target,
            )
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_platform_admin_biocs_delete_preview(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        names = [str(item) for item in (body.get("names") or [])]
        if not profile or not names:
            raise ValueError("profile and names required")
        result = await run_sync(plan_bioc_delete, profile, names)
        return JSONResponse(result)
    except (UnsupportedOperation, KeyError, ValueError) as exc:
        return error_response(exc, 400)


async def api_platform_admin_biocs_insert(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        biocs = [item for item in (body.get("biocs") or []) if isinstance(item, dict)]
        if not profile or not biocs:
            raise ValueError("profile and biocs required")
        resolved = get_profile(profile)
        result, status = await run_sync(admin_api.insert_biocs, resolved, biocs)
        await run_sync(refresh_section_cache, profile, "biocs")
        return JSONResponse({"profile": profile, "status": status, "result": result})
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_platform_admin_biocs_delete(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        names = [str(item) for item in (body.get("names") or [])]
        if not profile or not names:
            raise ValueError("profile and names required")
        resolved = get_profile(profile)
        results = await run_sync(admin_api.delete_biocs, resolved, names)
        await run_sync(refresh_section_cache, profile, "biocs")
        payload = {"profile": profile, "results": results}
        publish_delete_success_notifications(payload, title="BIOC delete", profile=profile)
        return JSONResponse(payload)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_platform_admin_correlation_delete_preview(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        names = [str(item) for item in (body.get("names") or [])]
        if not profile or not names:
            raise ValueError("profile and names required")
        result = await run_sync(plan_correlation_delete, profile, names)
        return JSONResponse(result)
    except (UnsupportedOperation, KeyError, ValueError) as exc:
        return error_response(exc, 400)


async def api_platform_admin_correlation_delete(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        names = [str(item) for item in (body.get("names") or [])]
        if not profile or not names:
            raise ValueError("profile and names required")
        resolved = get_profile(profile)
        results = await run_sync(admin_api.delete_correlation_rules, resolved, names)
        await run_sync(refresh_section_cache, profile, "correlation-rules")
        payload = {"profile": profile, "results": results}
        publish_delete_success_notifications(payload, title="Correlation rules delete", profile=profile)
        return JSONResponse(payload)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_platform_admin_indicators_copy_preview(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        source = str(body.get("source_profile") or "")
        target = str(body.get("target_profile") or "")
        ids = [str(item) for item in (body.get("ids") or [])]
        if not source or not target or not ids:
            raise ValueError("source_profile, target_profile, ids required")
        result = await run_sync(
            plan_indicator_copy,
            source,
            target,
            ids,
            overwrite=bool(body.get("overwrite")),
            stop_on_conflict=bool(body.get("stop_on_conflict")),
        )
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_platform_admin_indicators_copy(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        source = str(body.get("source_profile") or "")
        target = str(body.get("target_profile") or "")
        ids = [str(item) for item in (body.get("ids") or [])]
        if not source or not target or not ids:
            raise ValueError("source_profile, target_profile, ids required")
        result = await run_sync(
            copy_indicators_to_tenant,
            source,
            target,
            ids,
            overwrite=bool(body.get("overwrite")),
            stop_on_conflict=bool(body.get("stop_on_conflict")),
        )
        if result.get("executed"):
            publish_copy_success_notifications(
                result,
                title="Indicator copy",
                source=source,
                target=target,
            )
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_platform_admin_indicators_delete(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        ids = [str(item) for item in (body.get("ids") or [])]
        if not profile or not ids:
            raise ValueError("profile and ids required")
        resolved = get_profile(profile)
        result, status = await run_sync(admin_api.delete_indicators, resolved, ids)
        await run_sync(refresh_section_cache, profile, "indicators")
        payload = {
            "profile": profile,
            "results": [{"id": indicator_id, "status": status} for indicator_id in ids],
            "status": status,
            "result": result,
        }
        publish_delete_success_notifications(payload, title="Indicator delete", profile=profile)
        return JSONResponse(payload)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_platform_admin_api_keys_generate(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        comment = str(body.get("comment") or "cortex-ps-toolkit")
        roles = [str(item) for item in (body.get("roles") or []) if item]
        security_level = str(body.get("security_level") or "standard")
        expiration_raw = body.get("expiration")
        expiration = int(expiration_raw) if expiration_raw is not None else None
        if not profile:
            raise ValueError("profile required")
        if not roles:
            raise ValueError("roles required")
        resolved = get_profile(profile)
        result, status = await run_sync(
            admin_api.generate_api_key,
            resolved,
            comment,
            roles=roles,
            security_level=security_level,
            expiration=expiration,
        )
        await run_sync(refresh_section_cache, profile, "api-keys")
        return JSONResponse({"profile": profile, "status": status, "result": result})
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)


async def api_platform_admin_api_keys_delete(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        key_id = str(body.get("key_id") or "")
        if not profile or not key_id:
            raise ValueError("profile and key_id required")
        resolved = get_profile(profile)
        result, status = await run_sync(admin_api.delete_api_key, resolved, key_id)
        await run_sync(refresh_section_cache, profile, "api-keys")
        payload = {
            "profile": profile,
            "results": [{"key_id": key_id, "status": status}],
            "status": status,
            "result": result,
        }
        publish_delete_success_notifications(payload, title="API key delete", profile=profile)
        return JSONResponse(payload)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)
