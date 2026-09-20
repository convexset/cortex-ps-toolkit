from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.core.client import TenantApiError
from cortex_ps_toolkit.lists.delete import (
    delete_lists,
    friendly_delete_error,
    is_system_list,
    plan_lists_delete,
)


def test_is_system_list() -> None:
    assert is_system_list({"system": True}) is True
    assert is_system_list({"system": False}) is False
    assert is_system_list({}) is False


def test_friendly_delete_error_system_message() -> None:
    exc = TenantApiError("delete failed", status_code=400, body={"message": "Cannot delete system list"})
    assert friendly_delete_error(exc) == "System list cannot be deleted"


@patch("cortex_ps_toolkit.lists.delete.refresh_lists_cache")
@patch("cortex_ps_toolkit.lists.delete.find_list_in_index")
@patch("cortex_ps_toolkit.lists.delete.get_profile")
def test_plan_lists_delete_marks_system_lists(
    mock_get_profile: object,
    mock_find: object,
    mock_refresh: object,
) -> None:
    profile = type("P", (), {"slug": "lab", "tenant_type": object()})()
    mock_get_profile.return_value = profile

    def _find(_profile: object, *, list_id: str | None = None, name: str | None = None) -> dict | None:
        if list_id == "sys":
            return {"id": "sys", "name": "SystemList", "system": True}
        if list_id == "user":
            return {"id": "user", "name": "UserList", "system": False}
        return None

    mock_find.side_effect = _find

    with patch("cortex_ps_toolkit.lists.delete.assert_operation_supported"):
        plan = plan_lists_delete("lab", ["sys", "user"])

    assert plan["counts"] == {"total": 2, "delete": 1, "blocked_system": 1, "not_found": 0}
    assert plan["would_delete"] is True


@patch("cortex_ps_toolkit.lists.delete.refresh_lists_cache")
@patch("cortex_ps_toolkit.lists.delete.api.delete_list_by_id")
@patch("cortex_ps_toolkit.lists.delete.plan_lists_delete")
@patch("cortex_ps_toolkit.lists.delete.get_profile")
def test_delete_lists_blocks_system_and_deletes_user(
    mock_get_profile: object,
    mock_plan: object,
    mock_delete: object,
    mock_refresh: object,
) -> None:
    profile = type("P", (), {"slug": "lab", "tenant_type": object()})()
    mock_get_profile.return_value = profile
    mock_plan.return_value = {
        "profile": "lab",
        "items": [
            {"list_id": "sys", "name": "SystemList", "action": "blocked_system"},
            {"list_id": "user", "name": "UserList", "action": "delete"},
        ],
        "counts": {"total": 2, "delete": 1, "blocked_system": 1, "not_found": 0},
        "would_delete": True,
    }

    mock_delete.return_value = ({}, 200)

    with patch("cortex_ps_toolkit.lists.delete.assert_operation_supported"):
        result = delete_lists("lab", ["sys", "user"])

    mock_delete.assert_called_once_with(profile, "user")
    mock_refresh.assert_called_once_with(profile)
    assert result["counts"] == {"total": 2, "deleted": 1, "blocked": 1, "failed": 0, "not_found": 0}
    assert result["results"][0]["status"] == "blocked"
    assert result["results"][0]["reason"] == "System list cannot be deleted"
    assert result["results"][1]["status"] == "deleted"
    assert result["results"][1]["status_code"] == 200


@patch("cortex_ps_toolkit.lists.delete.refresh_lists_cache")
@patch("cortex_ps_toolkit.lists.delete.api.delete_list_by_id")
@patch("cortex_ps_toolkit.lists.delete.plan_lists_delete")
@patch("cortex_ps_toolkit.lists.delete.get_profile")
def test_delete_lists_reports_api_failure(
    mock_get_profile: object,
    mock_plan: object,
    mock_delete: object,
    mock_refresh: object,
) -> None:
    profile = type("P", (), {"slug": "lab", "tenant_type": object()})()
    mock_get_profile.return_value = profile
    mock_plan.return_value = {
        "profile": "lab",
        "items": [{"list_id": "user", "name": "UserList", "action": "delete"}],
        "counts": {"total": 1, "delete": 1, "blocked_system": 0, "not_found": 0},
        "would_delete": True,
    }
    mock_delete.side_effect = TenantApiError(
        "delete failed",
        status_code=403,
        body={"message": "Cannot delete system list"},
    )

    with patch("cortex_ps_toolkit.lists.delete.assert_operation_supported"):
        result = delete_lists("lab", ["user"])

    mock_refresh.assert_not_called()
    assert result["counts"]["failed"] == 1
    assert result["results"][0]["status"] == "failed"
    assert result["results"][0]["reason"] == "System list cannot be deleted"
    assert result["results"][0]["status_code"] == 403
