"""Tests for copy success WebSocket notifications."""

from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.server.copy_notifications import (
    copied_item_labels,
    maybe_publish_item_copied_from_progress,
    publish_copy_success_notifications,
    publish_item_copied_notification,
    publish_object_bundle_complete_notification,
)


def test_copied_item_labels_from_design_content_results() -> None:
    result = {
        "results": [
            {"source_id": "field-a", "target_name": "field-a", "status": 200, "action": "copy"},
            {"source_id": "field-b", "status": "skipped", "action": "skip"},
        ],
    }
    assert copied_item_labels(result) == ["field-a"]


def test_copied_item_labels_from_integrations_results() -> None:
    result = {
        "results": [
            {"integration_id": "MyCustomIntegration", "status": "copied"},
            {"integration_id": "Other", "status": "skipped"},
        ],
    }
    assert copied_item_labels(result) == ["MyCustomIntegration"]


def test_copied_item_labels_from_lists_results() -> None:
    result = {
        "results": [
            {"name": "My List", "status": "copied"},
            {"name": "Other", "status": "skipped"},
        ],
    }
    assert copied_item_labels(result) == ["My List"]


def test_copied_item_labels_from_object_bundle() -> None:
    result = {
        "assets": {
            "incident-fields": {
                "results": [{"target_name": "Field One", "status": 200}],
            },
            "layouts": {
                "results": [{"target_name": "Layout A", "status": 200}],
            },
        },
    }
    assert copied_item_labels(result) == ["incident-fields: Field One", "layouts: Layout A"]


@patch("cortex_ps_toolkit.server.copy_notifications.publish_notification")
def test_publish_item_copied_notification(mock_publish) -> None:
    publish_item_copied_notification(
        {"target_name": "Field One", "status": 200, "action": "copy"},
        asset="incident-fields",
        source="lab",
        target="dev",
    )
    mock_publish.assert_called_once()
    assert mock_publish.call_args.kwargs["auto_dismiss_ms"] == 5000
    assert mock_publish.call_args.kwargs["level"] == "success"
    message = mock_publish.call_args.args[0]
    assert "lab → dev" in message
    assert "incident-fields: Field One" in message


@patch("cortex_ps_toolkit.server.copy_notifications.publish_item_copied_notification")
def test_maybe_publish_item_copied_from_progress(mock_publish_item) -> None:
    maybe_publish_item_copied_from_progress(
        {
            "phase": "item_copied",
            "asset": "layouts",
            "entry": {"target_name": "Layout A", "status": 200},
        },
        source="lab",
        target="dev",
    )
    mock_publish_item.assert_called_once()


@patch("cortex_ps_toolkit.server.copy_notifications.publish_notification")
def test_publish_object_bundle_complete_notification(mock_publish) -> None:
    publish_object_bundle_complete_notification(
        {
            "assets": {
                "incident-fields": {"results": [{"target_name": "Field One", "status": 200}]},
            },
        },
        source="lab",
        target="dev",
    )
    mock_publish.assert_called_once()
    message = mock_publish.call_args.args[0]
    assert "Object Bundle copy complete (1 item)" in message


@patch("cortex_ps_toolkit.server.copy_notifications.publish_item_copied_notification")
def test_publish_copy_success_notifications_per_item(mock_publish_item) -> None:
    publish_copy_success_notifications(
        {
            "results": [
                {"name": "Rule A", "status": 200},
                {"name": "Rule B", "status": "skipped"},
            ],
        },
        title="Correlation copy",
        source="lab",
        target="dev",
    )
    mock_publish_item.assert_called_once()
    mock_publish_item.assert_called_with(
        {"name": "Rule A", "status": 200},
        asset="",
        source="lab",
        target="dev",
        title="Correlation copy",
    )


@patch("cortex_ps_toolkit.server.copy_notifications.publish_item_copied_notification")
@patch("cortex_ps_toolkit.server.copy_notifications.publish_notification")
def test_publish_copy_success_notifications_multiple_items(mock_publish, mock_publish_item) -> None:
    publish_copy_success_notifications(
        {
            "results": [
                {"name": "List A", "status": "copied"},
                {"name": "List B", "status": "updated"},
            ],
        },
        title="Lists copy",
        source="a",
        target="b",
    )
    assert mock_publish_item.call_count == 2
    mock_publish.assert_not_called()
