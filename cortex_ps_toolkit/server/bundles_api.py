"""REST handlers for Bundles section (extends object-setup bundle storage)."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..bundles.copy import copy_bundle_to_tenant, plan_bundle_copy
from ..content.copy_plan_params import copy_kwargs_from_body
from ..core.batch_copy_progress import chain_progress
from ..core.client import TenantApiError
from ..platforms import UnsupportedOperation
from .common import error_response, read_json, run_sync
from .copy_progress_http import http_staged_copy_progress, publish_standard_copy_outcome
from .object_setup_bundles_api import (
    api_object_setup_bundles_delete,
    api_object_setup_bundles_get,
    api_object_setup_bundles_list,
    api_object_setup_bundles_resolve,
    api_object_setup_bundles_save,
)


async def api_bundles_list(request: Request) -> JSONResponse:
    return await api_object_setup_bundles_list(request)


async def api_bundles_save(request: Request) -> JSONResponse:
    return await api_object_setup_bundles_save(request)


async def api_bundles_get(request: Request) -> JSONResponse:
    return await api_object_setup_bundles_get(request)


async def api_bundles_delete(request: Request) -> JSONResponse:
    return await api_object_setup_bundles_delete(request)


async def api_bundles_resolve(request: Request) -> JSONResponse:
    return await api_object_setup_bundles_resolve(request)


async def api_bundles_copy_preview(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        source = str(body.get("source_profile") or "")
        target = str(body.get("target_profile") or "")
        items = body.get("items") or []
        copy_kw = copy_kwargs_from_body(body)
        shallow_playbooks = bool(body.get("shallow_playbooks", True))
        if not source or not target or not items:
            raise ValueError("source_profile, target_profile, items required")
        plan = await run_sync(
            plan_bundle_copy,
            source,
            target,
            items,
            shallow_playbooks=shallow_playbooks,
            **copy_kw,
        )
        return JSONResponse(plan)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400 if isinstance(exc, UnsupportedOperation) else 404
        return error_response(exc, status)


async def api_bundles_copy(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        source = str(body.get("source_profile") or "")
        target = str(body.get("target_profile") or "")
        items = body.get("items") or []
        copy_kw = copy_kwargs_from_body(body)
        shallow_playbooks = bool(body.get("shallow_playbooks", True))
        if not source or not target or not items:
            raise ValueError("source_profile, target_profile, items required")
        title = "Bundle copy"
        on_progress = chain_progress(http_staged_copy_progress(title))
        result = await run_sync(
            copy_bundle_to_tenant,
            source,
            target,
            items,
            shallow_playbooks=shallow_playbooks,
            on_progress=on_progress,
            **copy_kw,
        )
        publish_standard_copy_outcome(result, title=title, source=source, target=target)
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400 if isinstance(exc, UnsupportedOperation) else 404
        return error_response(exc, status)
