"""App factory wrapper that patches index.html for profile context UI."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route

from ..paths import package_root
from .app import create_app as _create_app_base
from .profile_context_patch import patch_index_html


async def index_with_profile_context(_request: Request) -> HTMLResponse:
    path = package_root() / "web" / "static" / "index.html"
    html = path.read_text(encoding="utf-8")
    return HTMLResponse(patch_index_html(html))


def create_app():
    app = _create_app_base()
    routes = []
    for route in app.router.routes:
        if isinstance(route, Route) and route.path == "/":
            routes.append(Route("/", index_with_profile_context, methods=["GET"]))
        else:
            routes.append(route)
    app.router.routes = routes
    return app
