"""Shared server helpers."""

from __future__ import annotations

import asyncio
import json
import os
import traceback
from collections.abc import Callable
from typing import Any, TypeVar

from starlette.requests import Request
from starlette.responses import JSONResponse

T = TypeVar("T")


async def run_sync(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run blocking library/IO work in a thread so the event loop stays responsive."""
    return await asyncio.to_thread(func, *args, **kwargs)


async def read_json(request: Request) -> dict[str, Any]:
    if not request.headers.get("content-type", "").startswith("application/json"):
        return {}
    body = await request.body()
    if not body:
        return {}
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


def error_response(exc: Exception, status: int = 500) -> JSONResponse:
    payload: dict[str, Any] = {"error": str(exc)}
    if os.environ.get("CORTEX_PS_DEBUG"):
        payload["traceback"] = traceback.format_exc()
    return JSONResponse(payload, status_code=status)
