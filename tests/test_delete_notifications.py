"""Tests for delete success WebSocket notifications."""

from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.server.delete_notifications import (
    delete_entry_succeeded,
    publish_delete_success_notifications,
    publish_item_deleted_notification,
)


def test_delete_entry_succeeded_status_variants() -> None:
    assert delete_entry_succeeded({"status": "deleted"})
    assert delete_entry_succeeded({"status": 200})
    assert delete_entry_succeeded({"status": 204})
    assert not delete_entry_succeeded({"status": "failed"})
    assert not delete_entry_succeeded({"status": 404})


@patch("cortex_ps_toolkit.server.delete_notifications.publish_notification")
def test_publish_item_deleted_notification(mock_publish) -> None:
    publish_item_deleted_notification(
        {"name": "My List", "status": "deleted"},
        profile="lab",
        title="Lists delete",
    )
    mock_publish.assert_called_once()
    assert mock_publish.call_args.kwargs["auto_dismiss_ms"] == 5000
    assert mock_publish.call_args.kwargs["level"] == "success"
    message = mock_publish.call_args.args[0]
    assert "lab · Deleted: My List" in message


@patch("cortex_ps_toolkit.server.delete_notifications.publish_item_deleted_notification")
def test_publish_delete_success_notifications_per_item(mock_publish_item) -> None:
    publish_delete_success_notifications(
        {
            "profile": "lab",
            "results": [
                {"script_id": "sc1", "name": "PrintDebug", "status": "deleted"},
                {"script_id": "sc2", "name": "Builtin", "status": "blocked"},
            ],
        },
        title="Scripts delete",
        profile="lab",
    )
    mock_publish_item.assert_called_once()
    mock_publish_item.assert_called_with(
        {"script_id": "sc1", "name": "PrintDebug", "status": "deleted"},
        asset="",
        profile="lab",
        title="Scripts delete",
    )


@patch("cortex_ps_toolkit.server.delete_notifications.publish_item_deleted_notification")
@patch("cortex_ps_toolkit.server.delete_notifications.publish_notification")
def test_publish_delete_success_notifications_design_content(mock_publish, mock_publish_item) -> None:
    publish_delete_success_notifications(
        {
            "profile": "lab",
            "asset": "incident-fields",
            "results": [
                {"item_id": "field-a", "status": 200},
                {"item_id": "field-b", "status": 404},
            ],
        },
        title="Delete incident-fields",
        profile="lab",
        asset="incident-fields",
    )
    mock_publish_item.assert_called_once()
    message = mock_publish_item.call_args.kwargs
    assert message["asset"] == "incident-fields"


@patch("cortex_ps_toolkit.server.delete_notifications.publish_item_deleted_notification")
@patch("cortex_ps_toolkit.server.delete_notifications.publish_notification")
def test_publish_delete_success_notifications_multiple_items(mock_publish, mock_publish_item) -> None:
    publish_delete_success_notifications(
        {
            "profile": "lab",
            "results": [
                {"integration_id": "MyInt", "status": "deleted"},
                {"integration_id": "OtherInt", "status": "deleted"},
            ],
        },
        title="Integrations delete",
    )
    assert mock_publish_item.call_count == 2
    mock_publish.assert_not_called()
