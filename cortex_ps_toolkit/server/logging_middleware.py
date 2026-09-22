"""Log toolkit REST API read/write operations at INFO."""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from ..ops_log import log_data_read, log_data_write


class ToolkitLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            method = str(scope.get("method") or "")
            path = str(scope.get("path") or "")
            if path.startswith("/api/") and path not in ("/api/health",):
                detail = f"{method} {path}"
                if method in ("GET", "HEAD"):
                    log_data_read("toolkit API", detail=detail)
                elif method in ("POST", "PUT", "PATCH", "DELETE"):
                    log_data_write("toolkit API", detail=detail)
        await self.app(scope, receive, send)
