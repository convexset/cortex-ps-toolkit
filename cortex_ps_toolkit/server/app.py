"""Starlette application for Cortex PS Toolkit web UI."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Optional

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.types import Scope, Receive, Send

from ..core.client import TenantApiError
from ..credentials import get_profile
from ..content_capabilities import profile_capabilities
from ..lists.cache import load_lists_index
from .copy_notifications import publish_copy_success_notifications
from .delete_notifications import publish_delete_success_notifications
from ..lists.copy import copy_lists_to_tenant, plan_lists_copy
from ..lists.delete import delete_lists, plan_lists_delete
from ..cache.ensure import refresh_lists_cache_required, refresh_playbooks_cache_required, refresh_scripts_cache_required
from ..lists.service import list_cached_lists
from ..paths import package_root
from ..platforms import UnsupportedOperation
from ..playbooks.cache import load_playbooks_index
from ..playbooks.analysis import analyze_playbook
from ..playbooks.copy import copy_playbooks_to_tenant, plan_playbooks_copy
from ..playbooks.copy_components import (
    copy_playbook_components_to_tenant,
    plan_playbook_components_copy,
)
from ..playbooks.delete import delete_playbooks, plan_playbooks_delete
from ..playbooks.service import list_cached_playbooks
from ..scripts.cache import load_scripts_index
from ..scripts.copy import copy_scripts_to_tenant, plan_scripts_copy
from ..scripts.delete import delete_scripts, plan_scripts_delete
from ..scripts.service import list_cached_scripts
from ..integrations.copy import copy_integrations_to_tenant, plan_integrations_copy
from ..integrations.delete import delete_integrations, plan_integrations_delete
from ..cache.status import cache_scope_status
from ..settings import cache_ttl_seconds
from ..xql.service import run_xql_query
from . import credentials_api
from . import integrations_api
from . import lists_api
from . import scripts_api
from . import refactor_api
from . import design_content_api
from . import platform_admin_api
from . import vault_api
from .cache_api import api_cache_status, api_settings_get, api_settings_patch
from .xql_api import (
    api_xql_builtin_presets,
    api_xql_user_presets,
    api_xql_user_presets_delete,
    api_xql_user_presets_save,
)
from .common import error_response, read_json, run_sync
from .events import bind_event_loop
from .ws import websocket_endpoint
from .content_routes import (
    make_copy_handler,
    make_copy_preview_handler,
    make_delete_handler,
    make_delete_preview_handler,
    make_list_handler,
    make_refresh_handler,
)


async def api_health(_request: Request) -> JSONResponse:
    return JSONResponse({
        "ok": True,
        "service": "cortex-ps-toolkit",
        "docs": "/static/index.html",
    })


async def api_lists(request: Request) -> JSONResponse:
    profile = request.query_params.get("profile", "")
    if not profile:
        return JSONResponse({"error": "profile query parameter required"}, status_code=400)
    try:
        resolved = await run_sync(get_profile, profile)
        items = await run_sync(list_cached_lists, profile)
        cache_meta: dict = {}
        try:
            index = await run_sync(load_lists_index, resolved)
            cache_meta = cache_scope_status(index)
        except Exception:
            cache_meta = {}
        return JSONResponse({
            "profile": profile,
            "refreshed_at": cache_meta.get("refreshed_at"),
            "cache": cache_meta,
            "ttl_seconds": cache_ttl_seconds(),
            "lists": items,
            "count": len(items),
        })
    except KeyError as exc:
        return error_response(exc, 404)


async def api_lists_refresh(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        if not profile:
            return JSONResponse({"error": "profile required"}, status_code=400)
        result = await run_sync(refresh_lists_cache_required, profile)
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400 if isinstance(exc, UnsupportedOperation) else 404
        return error_response(exc, status)


def _parse_lists_copy_body(body: dict[str, Any]) -> tuple[str, str, list[str], bool, bool]:
    source = str(body.get("source_profile") or "")
    target = str(body.get("target_profile") or "")
    list_ids = [str(item) for item in (body.get("list_ids") or [])]
    overwrite = bool(body.get("overwrite"))
    stop_on_conflict = bool(body.get("stop_on_conflict"))
    if stop_on_conflict and overwrite:
        raise ValueError("overwrite and stop_on_conflict cannot both be enabled")
    if not source or not target or not list_ids:
        raise ValueError("source_profile, target_profile, list_ids required")
    return source, target, list_ids, overwrite, stop_on_conflict


async def api_lists_copy_preview(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        source, target, list_ids, overwrite, stop_on_conflict = _parse_lists_copy_body(body)
        plan = await run_sync(
            plan_lists_copy,
            source,
            target,
            list_ids,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
        )
        return JSONResponse(plan)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400 if isinstance(exc, UnsupportedOperation) else 404
        return error_response(exc, status)


def _parse_lists_delete_body(body: dict[str, Any]) -> tuple[str, list[str]]:
    profile = str(body.get("profile") or "")
    list_ids = [str(item) for item in (body.get("list_ids") or [])]
    if not profile or not list_ids:
        raise ValueError("profile and list_ids required")
    return profile, list_ids


async def api_lists_delete_preview(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile, list_ids = _parse_lists_delete_body(body)
        plan = await run_sync(plan_lists_delete, profile, list_ids)
        return JSONResponse(plan)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400 if isinstance(exc, UnsupportedOperation) else 404
        return error_response(exc, status)


async def api_lists_delete(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile, list_ids = _parse_lists_delete_body(body)
        result = await run_sync(delete_lists, profile, list_ids)
        publish_delete_success_notifications(result, title="Lists delete", profile=profile)
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400 if isinstance(exc, UnsupportedOperation) else 404
        return error_response(exc, status)


async def api_lists_copy(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        source, target, list_ids, overwrite, stop_on_conflict = _parse_lists_copy_body(body)
        result = await run_sync(
            copy_lists_to_tenant,
            source,
            target,
            list_ids,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
        )
        if not result.get("aborted"):
            publish_copy_success_notifications(
                result,
                title="Lists copy",
                source=source,
                target=target,
            )
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400 if isinstance(exc, UnsupportedOperation) else 404
        return error_response(exc, status)


async def api_playbooks_analysis(request: Request) -> JSONResponse:
    profile = request.query_params.get("profile", "")
    playbook_id = request.path_params.get("playbook_id", "")
    if not profile or not playbook_id:
        return JSONResponse({"error": "profile and playbook_id required"}, status_code=400)
    try:
        result = await run_sync(analyze_playbook, profile, playbook_id)
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400 if isinstance(exc, UnsupportedOperation) else 404
        return error_response(exc, status)


def _parse_playbook_components_body(body: dict[str, Any]) -> tuple[str, str, str, bool, bool]:
    source = str(body.get("source_profile") or "")
    target = str(body.get("target_profile") or "")
    playbook_id = str(body.get("playbook_id") or "")
    overwrite = bool(body.get("overwrite"))
    stop_on_conflict = bool(body.get("stop_on_conflict"))
    if stop_on_conflict and overwrite:
        raise ValueError("overwrite and stop_on_conflict cannot both be enabled")
    if not source or not target or not playbook_id:
        raise ValueError("source_profile, target_profile, playbook_id required")
    return source, target, playbook_id, overwrite, stop_on_conflict


async def api_playbooks_copy_components_preview(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        source, target, playbook_id, overwrite, stop_on_conflict = _parse_playbook_components_body(body)
        plan = await run_sync(
            plan_playbook_components_copy,
            source,
            target,
            playbook_id,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
        )
        return JSONResponse(plan)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400 if isinstance(exc, UnsupportedOperation) else 404
        return error_response(exc, status)


async def api_playbooks_copy_components(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        source, target, playbook_id, overwrite, stop_on_conflict = _parse_playbook_components_body(body)
        result = await run_sync(
            copy_playbook_components_to_tenant,
            source,
            target,
            playbook_id,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
        )
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400 if isinstance(exc, UnsupportedOperation) else 404
        return error_response(exc, status)


async def api_xql_run(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        query = str(body.get("query") or "").strip()
        if not profile or not query:
            return JSONResponse({"error": "profile and query required"}, status_code=400)
        timeframe = body.get("timeframe")
        if timeframe is not None and not isinstance(timeframe, dict):
            raise ValueError("timeframe must be an object when provided")
        result = await run_sync(
            run_xql_query,
            profile,
            query=query,
            timeframe=timeframe,
        )
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError, RuntimeError, TimeoutError) as exc:
        if isinstance(exc, TenantApiError):
            status = 502
        elif isinstance(exc, UnsupportedOperation):
            status = 400
        elif isinstance(exc, KeyError):
            status = 404
        elif isinstance(exc, TimeoutError):
            status = 504
        else:
            status = 400
        return error_response(exc, status)


class DevNoCacheStaticFiles(StaticFiles):
    """Serve static assets without browser caching in dev."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"cache-control", b"no-store, max-age=0"))
                message = {**message, "headers": headers}
            await send(message)

        await super().__call__(scope, receive, send_wrapper)


async def api_profile_capabilities(request: Request) -> JSONResponse:
    profile = request.query_params.get("profile", "")
    if not profile:
        return JSONResponse({"error": "profile query parameter required"}, status_code=400)
    try:
        return JSONResponse(profile_capabilities(profile))
    except KeyError as exc:
        return error_response(exc, 404)


async def index(_request: Request) -> FileResponse:
    return FileResponse(
        package_root() / "web" / "static" / "index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


async def favicon(_request: Request) -> FileResponse:
    return FileResponse(
        package_root() / "web" / "static" / "logo.png",
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@asynccontextmanager
async def _app_lifespan(_app: Starlette):
    bind_event_loop(asyncio.get_running_loop())
    yield


def create_app() -> Starlette:
    from ..ops_log import configure_ops_logging

    configure_ops_logging()
    static_dir = package_root() / "web" / "static"
    routes: list[Any] = [
        Route("/", index),
        Route("/favicon.ico", favicon),
        Route("/api/health", api_health, methods=["GET"]),
        Route("/api/credentials", credentials_api.api_credentials_list, methods=["GET"]),
        Route("/api/credentials", credentials_api.api_credentials_create, methods=["POST"]),
        Route("/api/credentials/import-lab", credentials_api.api_credentials_import_lab, methods=["POST"]),
        Route("/api/credentials/purge-expired", credentials_api.api_credentials_purge_expired, methods=["POST"]),
        Route("/api/credentials/{slug}", credentials_api.api_credentials_get, methods=["GET"]),
        Route("/api/credentials/{slug}", credentials_api.api_credentials_update, methods=["PUT"]),
        Route("/api/credentials/{slug}", credentials_api.api_credentials_delete, methods=["DELETE"]),
        Route("/api/credentials/{slug}/validate", credentials_api.api_credentials_validate, methods=["POST"]),
        Route("/api/credentials/{slug}/expiry", credentials_api.api_credentials_expiry, methods=["POST"]),
        Route("/api/credentials/{slug}/verify-ssl", credentials_api.api_credentials_verify_ssl, methods=["POST"]),
        Route("/api/lists", api_lists, methods=["GET"]),
        Route("/api/lists/refresh", api_lists_refresh, methods=["POST"]),
        Route("/api/lists/delete/preview", api_lists_delete_preview, methods=["POST"]),
        Route("/api/lists/delete", api_lists_delete, methods=["POST"]),
        Route("/api/lists/copy/preview", api_lists_copy_preview, methods=["POST"]),
        Route("/api/lists/copy", api_lists_copy, methods=["POST"]),
        Route("/api/lists/{list_id}", lists_api.api_list_detail, methods=["GET"]),
        Route(
            "/api/playbooks",
            make_list_handler(
                list_cached=list_cached_playbooks,
                load_index=load_playbooks_index,
                items_key="playbooks",
            ),
            methods=["GET"],
        ),
        Route("/api/playbooks/refresh", make_refresh_handler(refresh_playbooks_cache_required), methods=["POST"]),
        Route(
            "/api/playbooks/{playbook_id}/analysis",
            api_playbooks_analysis,
            methods=["GET"],
        ),
        Route(
            "/api/playbooks/copy/preview",
            make_copy_preview_handler(plan_playbooks_copy, ids_key="playbook_ids"),
            methods=["POST"],
        ),
        Route(
            "/api/playbooks/copy-components/preview",
            api_playbooks_copy_components_preview,
            methods=["POST"],
        ),
        Route(
            "/api/playbooks/copy-components",
            api_playbooks_copy_components,
            methods=["POST"],
        ),
        Route(
            "/api/playbooks/refactor/presets",
            refactor_api.api_playbooks_refactor_presets,
            methods=["GET"],
        ),
        Route(
            "/api/playbooks/refactor/presets/{preset_id}",
            refactor_api.api_playbooks_refactor_preset_get,
            methods=["GET"],
        ),
        Route(
            "/api/playbooks/refactor/workflow",
            refactor_api.api_playbooks_refactor_workflow,
            methods=["POST"],
        ),
        Route(
            "/api/playbooks/refactor/validate-extract",
            refactor_api.api_playbooks_refactor_validate_extract,
            methods=["POST"],
        ),
        Route(
            "/api/playbooks/refactor/preview",
            refactor_api.api_playbooks_refactor_preview,
            methods=["POST"],
        ),
        Route(
            "/api/playbooks/refactor/execute",
            refactor_api.api_playbooks_refactor_execute,
            methods=["POST"],
        ),
        Route(
            "/api/playbooks/refactor/update-tasks/preview",
            refactor_api.api_playbooks_refactor_update_tasks_preview,
            methods=["POST"],
        ),
        Route(
            "/api/playbooks/refactor/update-tasks",
            refactor_api.api_playbooks_refactor_update_tasks,
            methods=["POST"],
        ),
        Route(
            "/api/playbooks/copy",
            make_copy_handler(copy_playbooks_to_tenant, ids_key="playbook_ids", copy_title="Playbooks copy"),
            methods=["POST"],
        ),
        Route(
            "/api/playbooks/delete/preview",
            make_delete_preview_handler(plan_playbooks_delete, ids_key="playbook_ids"),
            methods=["POST"],
        ),
        Route(
            "/api/playbooks/delete",
            make_delete_handler(delete_playbooks, ids_key="playbook_ids", delete_title="Playbooks delete"),
            methods=["POST"],
        ),
        Route(
            "/api/scripts",
            make_list_handler(
                list_cached=list_cached_scripts,
                load_index=load_scripts_index,
                items_key="scripts",
            ),
            methods=["GET"],
        ),
        Route("/api/scripts/refresh", make_refresh_handler(refresh_scripts_cache_required), methods=["POST"]),
        Route(
            "/api/scripts/copy/preview",
            make_copy_preview_handler(plan_scripts_copy, ids_key="script_ids"),
            methods=["POST"],
        ),
        Route(
            "/api/scripts/copy",
            make_copy_handler(copy_scripts_to_tenant, ids_key="script_ids", copy_title="Scripts copy"),
            methods=["POST"],
        ),
        Route(
            "/api/scripts/delete/preview",
            make_delete_preview_handler(plan_scripts_delete, ids_key="script_ids"),
            methods=["POST"],
        ),
        Route(
            "/api/scripts/delete",
            make_delete_handler(delete_scripts, ids_key="script_ids", delete_title="Scripts delete"),
            methods=["POST"],
        ),
        Route("/api/scripts/{script_id}", scripts_api.api_script_detail, methods=["GET"]),
        Route("/api/xql/run", api_xql_run, methods=["POST"]),
        Route("/api/xql/presets/builtin", api_xql_builtin_presets, methods=["GET"]),
        Route("/api/xql/presets/user", api_xql_user_presets, methods=["GET"]),
        Route("/api/xql/presets/user", api_xql_user_presets_save, methods=["POST"]),
        Route("/api/xql/presets/user/{preset_id}", api_xql_user_presets_delete, methods=["DELETE"]),
        Route("/api/integrations/commands", integrations_api.api_integrations_commands, methods=["GET"]),
        Route(
            "/api/integrations/commands/{integration_id}",
            integrations_api.api_integrations_commands_detail,
            methods=["GET"],
        ),
        Route("/api/integrations/instances", integrations_api.api_integrations_instances, methods=["GET"]),
        Route(
            "/api/integrations/tenant-credentials",
            integrations_api.api_integrations_tenant_credentials,
            methods=["GET"],
        ),
        Route("/api/integrations/packs", integrations_api.api_integrations_packs, methods=["GET"]),
        Route("/api/integrations/refresh", integrations_api.api_integrations_refresh, methods=["POST"]),
        Route(
            "/api/integrations/configurations",
            integrations_api.api_integrations_configurations,
            methods=["GET"],
        ),
        Route(
            "/api/integrations/definitions/{integration_id}",
            integrations_api.api_integrations_definition_detail,
            methods=["GET"],
        ),
        Route(
            "/api/integrations/instances/{instance_id}",
            integrations_api.api_integrations_instance_detail,
            methods=["GET"],
        ),
        Route(
            "/api/integrations/copy/preview",
            make_copy_preview_handler(plan_integrations_copy, ids_key="integration_ids"),
            methods=["POST"],
        ),
        Route(
            "/api/integrations/copy",
            make_copy_handler(
                copy_integrations_to_tenant,
                ids_key="integration_ids",
                copy_title="Integrations copy",
            ),
            methods=["POST"],
        ),
        Route(
            "/api/integrations/delete/preview",
            make_delete_preview_handler(plan_integrations_delete, ids_key="integration_ids"),
            methods=["POST"],
        ),
        Route(
            "/api/integrations/delete",
            make_delete_handler(delete_integrations, ids_key="integration_ids", delete_title="Integrations delete"),
            methods=["POST"],
        ),
        Route(
            "/api/design-content/{asset}",
            design_content_api.api_design_content_list,
            methods=["GET"],
        ),
        Route(
            "/api/design-content/{asset}/{item_id}",
            design_content_api.api_design_content_get_one,
            methods=["GET"],
        ),
        Route(
            "/api/design-content/refresh",
            design_content_api.api_design_content_refresh,
            methods=["POST"],
        ),
        Route(
            "/api/design-content/{asset}/copy/preview",
            design_content_api.api_design_content_copy_preview,
            methods=["POST"],
        ),
        Route(
            "/api/design-content/{asset}/copy",
            design_content_api.api_design_content_copy,
            methods=["POST"],
        ),
        Route(
            "/api/design-content/{asset}/delete/preview",
            design_content_api.api_design_content_delete_preview,
            methods=["POST"],
        ),
        Route(
            "/api/design-content/{asset}/delete",
            design_content_api.api_design_content_delete,
            methods=["POST"],
        ),
        Route(
            "/api/design-content/orchestrate",
            design_content_api.api_design_content_orchestrate,
            methods=["POST"],
        ),
        Route(
            "/api/platform-admin/{section}",
            platform_admin_api.api_platform_admin_list,
            methods=["GET"],
        ),
        Route(
            "/api/platform-admin/refresh",
            platform_admin_api.api_platform_admin_refresh,
            methods=["POST"],
        ),
        Route(
            "/api/profile/capabilities",
            api_profile_capabilities,
            methods=["GET"],
        ),
        Route(
            "/api/platform-admin/correlation-rules/copy/preview",
            platform_admin_api.api_platform_admin_correlation_copy_preview,
            methods=["POST"],
        ),
        Route(
            "/api/platform-admin/correlation-rules/copy",
            platform_admin_api.api_platform_admin_correlation_copy,
            methods=["POST"],
        ),
        Route(
            "/api/platform-admin/correlation-rules/delete/preview",
            platform_admin_api.api_platform_admin_correlation_delete_preview,
            methods=["POST"],
        ),
        Route(
            "/api/platform-admin/correlation-rules/delete",
            platform_admin_api.api_platform_admin_correlation_delete,
            methods=["POST"],
        ),
        Route(
            "/api/platform-admin/biocs/copy/preview",
            platform_admin_api.api_platform_admin_biocs_copy_preview,
            methods=["POST"],
        ),
        Route(
            "/api/platform-admin/biocs/copy",
            platform_admin_api.api_platform_admin_biocs_copy,
            methods=["POST"],
        ),
        Route(
            "/api/platform-admin/biocs/delete/preview",
            platform_admin_api.api_platform_admin_biocs_delete_preview,
            methods=["POST"],
        ),
        Route(
            "/api/platform-admin/biocs/insert",
            platform_admin_api.api_platform_admin_biocs_insert,
            methods=["POST"],
        ),
        Route(
            "/api/platform-admin/biocs/delete",
            platform_admin_api.api_platform_admin_biocs_delete,
            methods=["POST"],
        ),
        Route(
            "/api/platform-admin/indicators/copy/preview",
            platform_admin_api.api_platform_admin_indicators_copy_preview,
            methods=["POST"],
        ),
        Route(
            "/api/platform-admin/indicators/copy",
            platform_admin_api.api_platform_admin_indicators_copy,
            methods=["POST"],
        ),
        Route(
            "/api/platform-admin/indicators/delete",
            platform_admin_api.api_platform_admin_indicators_delete,
            methods=["POST"],
        ),
        Route(
            "/api/platform-admin/api-keys/generate",
            platform_admin_api.api_platform_admin_api_keys_generate,
            methods=["POST"],
        ),
        Route(
            "/api/platform-admin/api-keys/delete",
            platform_admin_api.api_platform_admin_api_keys_delete,
            methods=["POST"],
        ),
        Route("/api/vault/status", vault_api.api_vault_status, methods=["GET"]),
        Route("/api/vault/init", vault_api.api_vault_init, methods=["POST"]),
        Route("/api/vault/unlock", vault_api.api_vault_unlock, methods=["POST"]),
        Route("/api/vault/lock", vault_api.api_vault_lock, methods=["POST"]),
        Route("/api/vault/wraps", vault_api.api_vault_wraps, methods=["GET"]),
        Route("/api/vault/wraps", vault_api.api_vault_wrap_add, methods=["POST"]),
        Route("/api/vault/wraps/revoke", vault_api.api_vault_wrap_revoke, methods=["POST"]),
        Route("/api/vault/entries", vault_api.api_vault_entries, methods=["GET"]),
        Route("/api/vault/entries", vault_api.api_vault_entries_create, methods=["POST"]),
        Route("/api/cache/status", api_cache_status, methods=["GET"]),
        Route("/api/settings", api_settings_get, methods=["GET"]),
        Route("/api/settings", api_settings_patch, methods=["PATCH"]),
        WebSocketRoute("/ws", websocket_endpoint),
    ]
    if static_dir.is_dir():
        routes.append(Mount("/static", DevNoCacheStaticFiles(directory=str(static_dir)), name="static"))

    app = Starlette(routes=routes, lifespan=_app_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:*", "http://localhost:*"],
        allow_origin_regex=r"https?://(127\.0\.0\.1|localhost)(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app
