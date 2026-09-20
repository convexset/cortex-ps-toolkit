"""HTTP handlers for playbook refactor (extract-multi + task updates)."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..core.client import TenantApiError
from ..platforms import UnsupportedOperation
from ..playbooks.refactor import (
    execute_refactor,
    execute_task_updates,
    plan_refactor,
    plan_task_updates,
)
from ..playbooks.refactor_bridge import playbook_utils_runtime
from ..playbooks.refactor_graph_validation import validate_cluster_extract, validate_leaf_extract
from ..playbooks.refactor_presets import get_refactor_preset, list_refactor_presets
from ..playbooks.refactor_workflow import execute_refactor_workflow
from .common import error_response, read_json, run_sync


def _str_list(value: Any) -> list[str]:
    if not value:
        return []
    if not isinstance(value, list):
        raise ValueError("Expected a JSON array of strings")
    return [str(item) for item in value]


def _optional_str(body: dict[str, Any], key: str) -> str | None:
    raw = body.get(key)
    if raw is None or raw == "":
        return None
    return str(raw)


async def api_playbooks_refactor_presets(_request: Request) -> JSONResponse:
    return JSONResponse({"presets": list_refactor_presets()})


async def api_playbooks_refactor_preset_get(request: Request) -> JSONResponse:
    preset_id = request.path_params["preset_id"]
    try:
        preset = await run_sync(get_refactor_preset, preset_id)
        return JSONResponse(preset)
    except KeyError as exc:
        return error_response(exc, 404)


async def api_playbooks_refactor_workflow(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        preset_id = str(body.get("preset_id") or body.get("preset") or "")
        if not preset_id:
            return JSONResponse({"error": "preset_id required"}, status_code=400)
        refactor_mode = body.get("refactor_mode")
        result = await run_sync(
            execute_refactor_workflow,
            preset_id,
            skip_clear=bool(body.get("skip_clear")),
            refactor_mode=str(refactor_mode) if refactor_mode else None,
        )
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError, RuntimeError) as exc:
        return error_response(exc, _status_for_exc(exc))


async def api_playbooks_refactor_validate_extract(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        playbook_id = _optional_str(body, "playbook_id")
        kind = str(body.get("kind") or "").strip().lower()
        if not profile or not playbook_id:
            return JSONResponse({"error": "profile and playbook_id required"}, status_code=400)
        if kind not in {"leaf", "cluster"}:
            return JSONResponse({"error": "kind must be leaf or cluster"}, status_code=400)

        with playbook_utils_runtime(profile, operation_id="playbooks.refactor.validate_extract") as (
            _profile,
            _creds,
            _client,
            cache,
            _policy,
        ):
            playbook = cache.resolve(playbook_id)
            if kind == "leaf":
                result = validate_leaf_extract(
                    playbook,
                    str(body.get("task_id") or ""),
                    other_leaf_task_ids=_str_list(body.get("other_leaf_tasks")),
                )
            else:
                result = validate_cluster_extract(
                    playbook,
                    str(body.get("start_id") or ""),
                    str(body.get("end_id") or ""),
                )
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError, RuntimeError) as exc:
        return error_response(exc, _status_for_exc(exc))


async def api_playbooks_refactor_preview(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        if not profile:
            return JSONResponse({"error": "profile required"}, status_code=400)
        plan = await run_sync(
            plan_refactor,
            profile,
            playbook_id=_optional_str(body, "playbook_id"),
            playbook_name=_optional_str(body, "playbook_name"),
            leaf_tasks=_str_list(body.get("leaf_tasks")),
            clusters=_str_list(body.get("clusters")),
            post_task_updates=_str_list(body.get("post_task_updates")),
            parent_copy_name=_optional_str(body, "parent_copy_name"),
            force=bool(body.get("force")),
        )
        return JSONResponse(plan)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError, RuntimeError) as exc:
        status = _status_for_exc(exc)
        return error_response(exc, status)


async def api_playbooks_refactor_execute(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        if not profile:
            return JSONResponse({"error": "profile required"}, status_code=400)
        result = await run_sync(
            execute_refactor,
            profile,
            playbook_id=_optional_str(body, "playbook_id"),
            playbook_name=_optional_str(body, "playbook_name"),
            leaf_tasks=_str_list(body.get("leaf_tasks")),
            clusters=_str_list(body.get("clusters")),
            post_task_updates=_str_list(body.get("post_task_updates")),
            parent_copy_name=_optional_str(body, "parent_copy_name"),
            damp_run=bool(body.get("damp_run")),
            upload_only=bool(body.get("upload_only")),
            upload_parent_on_mismatch=bool(body.get("upload_parent_on_mismatch")),
            require_match=bool(body.get("require_match")),
            force=bool(body.get("force")),
            refactor_mode=str(body["refactor_mode"]) if body.get("refactor_mode") else None,
        )
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError, RuntimeError) as exc:
        status = _status_for_exc(exc)
        return error_response(exc, status)


async def api_playbooks_refactor_update_tasks_preview(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        if not profile:
            return JSONResponse({"error": "profile required"}, status_code=400)
        plan = await run_sync(
            plan_task_updates,
            profile,
            playbook=_optional_str(body, "playbook"),
            name_prefix=_optional_str(body, "name_prefix"),
            updates=_str_list(body.get("updates")),
            context_updates=_str_list(body.get("context_updates")),
            match_task_names=_str_list(body.get("match_task_names")),
            match_update=_optional_str(body, "match_update"),
            force=bool(body.get("force")),
        )
        return JSONResponse(plan)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError, RuntimeError) as exc:
        status = _status_for_exc(exc)
        return error_response(exc, status)


async def api_playbooks_refactor_update_tasks(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        profile = str(body.get("profile") or "")
        if not profile:
            return JSONResponse({"error": "profile required"}, status_code=400)
        result = await run_sync(
            execute_task_updates,
            profile,
            playbook=_optional_str(body, "playbook"),
            name_prefix=_optional_str(body, "name_prefix"),
            updates=_str_list(body.get("updates")),
            context_updates=_str_list(body.get("context_updates")),
            match_task_names=_str_list(body.get("match_task_names")),
            match_update=_optional_str(body, "match_update"),
            dry_run=bool(body.get("dry_run")),
            force=bool(body.get("force")),
        )
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError, RuntimeError) as exc:
        status = _status_for_exc(exc)
        return error_response(exc, status)


def _status_for_exc(exc: BaseException) -> int:
    if isinstance(exc, TenantApiError):
        return 502
    if isinstance(exc, UnsupportedOperation):
        return 400
    if isinstance(exc, KeyError):
        return 404
    if isinstance(exc, RuntimeError):
        return 503
    return 400
