"""HTTP tests for vault API routes."""

from __future__ import annotations

from starlette.testclient import TestClient

from cortex_ps_toolkit.server.app import create_app


def test_vault_status_returns_json() -> None:
    client = TestClient(create_app())
    response = client.get("/api/vault/status")
    assert response.status_code == 200
    payload = response.json()
    assert "locked" in payload
