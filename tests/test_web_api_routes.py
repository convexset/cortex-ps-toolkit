"""Smoke test: refactor routes are registered on the Starlette app."""

from __future__ import annotations

from cortex_ps_toolkit.server.app import create_app


def test_refactor_routes_registered() -> None:
    app = create_app()
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/api/playbooks/refactor/presets" in paths
    assert "/api/playbooks/refactor/workflow" in paths
    assert "/api/playbooks/refactor/preview" in paths
    assert "/api/playbooks/refactor/execute" in paths
    assert "/api/playbooks/refactor/update-tasks/preview" in paths
    assert "/api/playbooks/refactor/update-tasks" in paths
    assert "/api/design-content/{asset}" in paths
    assert "/api/design-content/refresh" in paths
    assert "/api/design-content/{asset}/copy" in paths
    assert "/api/design-content/orchestrate" in paths
    assert "/api/platform-admin/{section}" in paths
    assert "/api/platform-admin/refresh" in paths
    assert "/api/profile/capabilities" in paths
    assert "/api/platform-admin/correlation-rules/copy/preview" in paths
    assert "/api/platform-admin/correlation-rules/copy" in paths
    assert "/api/platform-admin/correlation-rules/delete/preview" in paths
    assert "/api/platform-admin/correlation-rules/delete" in paths
    assert "/api/platform-admin/biocs/copy/preview" in paths
    assert "/api/platform-admin/biocs/copy" in paths
    assert "/api/platform-admin/biocs/delete/preview" in paths
    assert "/api/platform-admin/indicators/copy/preview" in paths
    assert "/api/platform-admin/indicators/copy" in paths
    assert "/api/platform-admin/indicators/delete" in paths
    assert "/api/platform-admin/biocs/delete" in paths
    assert "/api/design-content/{asset}/delete" in paths
    assert "/api/vault/status" in paths
