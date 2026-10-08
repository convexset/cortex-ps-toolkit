"""Offline E2E: preview → operation plan → confirm-shaped JSON."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from starlette.testclient import TestClient

from cortex_ps_toolkit.server.app import create_app


@patch("cortex_ps_toolkit.server.app.plan_lists_delete")
def test_lists_delete_preview_plan_version(mock_plan) -> None:
    client = TestClient(create_app())
    mock_plan.return_value = {
        "profile": "lab",
        "items": [{"list_id": "x", "name": "X", "action": "delete"}],
        "counts": {"total": 1, "delete": 1, "blocked_system": 0, "not_found": 0},
        "would_delete": True,
    }
    response = client.post("/api/lists/delete/preview", json={"profile": "lab", "list_ids": ["x"]})
    assert response.status_code == 200
    body = response.json()
    assert body["plan_version"] == 1
    assert body["would_delete"] is True
    assert body["summary"]["delete"] == 1


@patch("cortex_ps_toolkit.content.name_check.get_profile")
@patch("cortex_ps_toolkit.content.name_check.find_list_in_index")
def test_name_check_api(mock_find, mock_profile) -> None:
    client = TestClient(create_app())
    mock_profile.return_value.slug = "tgt"
    mock_find.return_value = None
    response = client.post(
        "/api/copy/name-check",
        json={
            "target_profile": "tgt",
            "kind": "lists",
            "proposals": [{"key": "id1", "source_name": "A", "proposed_name": "A_copy"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["all_available"] is True


@patch("cortex_ps_toolkit.platform_admin.plan.plan_indicator_delete")
def test_indicators_delete_preview_plan_version(mock_plan) -> None:
    client = TestClient(create_app())
    mock_plan.return_value = {
        "profile": "lab",
        "section": "indicators",
        "entries": [{"id": "114", "deletable": True}],
    }
    response = client.post(
        "/api/platform-admin/indicators/delete/preview",
        json={"profile": "lab", "ids": ["114"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["plan_version"] == 1
    assert body["summary"]["delete"] == 1
    assert body["items"][0]["name"] == "114"


@patch("cortex_ps_toolkit.server.app.plan_playbook_components_copy")
def test_copy_components_preview_plan_shape(mock_plan) -> None:
    from cortex_ps_toolkit.content.operation_plan import wrap_copy_plan

    client = TestClient(create_app())
    legacy = {
        "source_profile": "src",
        "target_profile": "tgt",
        "items": [],
        "scripts": {"items": []},
        "playbooks": {"items": []},
        "would_abort": False,
    }
    mock_plan.return_value = wrap_copy_plan(
        {**legacy, "items": [{"name": "Root", "action": "copy"}]},
        operation="playbooks.copy_components",
        mode="skip",
    )
    response = client.post(
        "/api/playbooks/copy-components/preview",
        json={
            "source_profile": "src",
            "target_profile": "tgt",
            "playbook_id": "pb-1",
        },
    )
    assert response.status_code == 200
    assert response.json()["plan_version"] == 1
