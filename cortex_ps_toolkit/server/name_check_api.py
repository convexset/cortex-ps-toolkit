"""HTTP handler for copy name-check API."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..content.copy_plan_params import copy_kwargs_from_body
from ..content.name_check import NameCheckKind, check_proposed_names, proposals_from_copy_selection
from .common import error_response, read_json, run_sync
from ..core.client import TenantApiError
from ..platforms import UnsupportedOperation


async def api_copy_name_check(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        target_profile = str(body.get("target_profile") or "")
        kind = str(body.get("kind") or "").strip().lower()
        if kind not in ("lists", "scripts", "playbooks", "design"):
            raise ValueError("kind must be lists, scripts, playbooks, or design")
        if not target_profile:
            raise ValueError("target_profile required")

        asset = str(body.get("asset") or "").strip() or None
        proposals_raw = body.get("proposals")
        if isinstance(proposals_raw, list) and proposals_raw:
            proposals = [dict(row) for row in proposals_raw if isinstance(row, dict)]
        else:
            items = [dict(row) for row in (body.get("items") or []) if isinstance(row, dict)]
            if not items:
                raise ValueError("proposals or items required")
            opts = copy_kwargs_from_body(body)
            proposals = proposals_from_copy_selection(
                kind=kind,  # type: ignore[arg-type]
                items=items,
                rename_suffix=str(opts.get("rename_suffix") or ""),
                rename_map=opts.get("rename_map"),
            )
        result = await run_sync(
            check_proposed_names,
            target_profile,
            kind,  # type: ignore[arg-type]
            proposals,
            asset=asset,
        )
        return JSONResponse(result)
    except (TenantApiError, UnsupportedOperation, KeyError, ValueError) as exc:
        status = 502 if isinstance(exc, TenantApiError) else 400
        return error_response(exc, status)
