"""HTTP API tests for refactor workflow and preset listing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from cortex_ps_toolkit.server.app import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_refactor_presets_lists_single_and_workflow_configs(client: TestClient) -> None:
    response = client.get("/api/playbooks/refactor/presets")
    assert response.status_code == 200
    presets = response.json()["presets"]
    ids = {item["id"] for item in presets}
    assert "mfec-uat-splunk-phishing" in ids
    assert "mfec-uat-full-workflow" in ids
    workflow = next(item for item in presets if item["id"] == "mfec-uat-full-workflow")
    assert workflow.get("steps")


@patch("cortex_ps_toolkit.server.refactor_api.execute_refactor_workflow")
def test_refactor_workflow_api(mock_execute: MagicMock, client: TestClient) -> None:
    mock_execute.return_value = {
        "preset_id": "mfec-uat-full-workflow",
        "ok": True,
        "total_elapsed_ms": 1000,
        "steps": [],
    }
    response = client.post(
        "/api/playbooks/refactor/workflow",
        json={"preset_id": "mfec-uat-full-workflow", "refactor_mode": "parallel"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    mock_execute.assert_called_once()
    assert mock_execute.call_args.args[0] == "mfec-uat-full-workflow"
    assert mock_execute.call_args.kwargs["refactor_mode"] == "parallel"


def test_refactor_workflow_api_requires_preset_id(client: TestClient) -> None:
    response = client.post("/api/playbooks/refactor/workflow", json={})
    assert response.status_code == 400
    assert "preset_id" in response.json()["error"].lower()


@patch("cortex_ps_toolkit.server.refactor_api.playbook_utils_runtime")
@patch("cortex_ps_toolkit.server.refactor_api.validate_leaf_extract")
def test_refactor_validate_extract_leaf_api(
    mock_validate: MagicMock,
    mock_runtime: MagicMock,
    client: TestClient,
) -> None:
    mock_cache = MagicMock()
    mock_cache.resolve.return_value = {"name": "Test_PB", "tasks": {}}
    mock_runtime.return_value.__enter__.return_value = (None, None, None, mock_cache, None)
    mock_validate.return_value = {"ok": True, "reasons": [], "task_id": "2"}

    response = client.post(
        "/api/playbooks/refactor/validate-extract",
        json={"profile": "lab", "playbook_id": "pb-1", "kind": "leaf", "task_id": "2"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    mock_validate.assert_called_once()


@patch("cortex_ps_toolkit.server.refactor_api.plan_refactor")
def test_refactor_preview_api(mock_plan: MagicMock, client: TestClient) -> None:
    mock_plan.return_value = {
        "profile": "lab",
        "playbook_name": "Test_PB",
        "leaf_tasks": ["1"],
        "clusters": [],
        "post_task_updates": [],
    }
    response = client.post(
        "/api/playbooks/refactor/preview",
        json={
            "profile": "lab",
            "playbook_name": "Test_PB",
            "leaf_tasks": ["1"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["playbook_name"] == "Test_PB"
    mock_plan.assert_called_once()
    assert mock_plan.call_args.args[0] == "lab"


@patch("cortex_ps_toolkit.server.refactor_api.execute_refactor")
def test_refactor_execute_api(mock_execute: MagicMock, client: TestClient) -> None:
    mock_execute.return_value = {
        "ok": True,
        "parent_copy_name": "[REFACTOR-M] Test_PB",
        "timing": {"total_elapsed_ms": 5000},
        "compares": [{"equal": True}],
    }
    response = client.post(
        "/api/playbooks/refactor/execute",
        json={
            "profile": "lab",
            "playbook_name": "Test_PB",
            "leaf_tasks": ["366"],
            "refactor_mode": "parallel",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    mock_execute.assert_called_once()
    assert mock_execute.call_args.args[0] == "lab"
    assert mock_execute.call_args.kwargs["refactor_mode"] == "parallel"


def test_refactor_preview_api_requires_profile(client: TestClient) -> None:
    response = client.post("/api/playbooks/refactor/preview", json={"playbook_name": "X"})
    assert response.status_code == 400
    assert "profile" in response.json()["error"].lower()


def test_refactor_execute_api_requires_profile(client: TestClient) -> None:
    response = client.post("/api/playbooks/refactor/execute", json={"playbook_name": "X"})
    assert response.status_code == 400
    assert "profile" in response.json()["error"].lower()
