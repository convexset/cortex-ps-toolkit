"""Copy completion notification flattening."""

from __future__ import annotations

from cortex_ps_toolkit.server.copy_notifications import (
    _flatten_batch_copy_rows,
    publish_batch_copy_complete_notification,
)


def test_flatten_bundle_copy_nested_results() -> None:
    result = {
        "operation": "bundles.copy",
        "results": {
            "integrations": {
                "results": [{"integration_id": "A", "status": "copied", "name": "A"}],
            },
            "design": {
                "executed": True,
                "assets": {
                    "incident-types": {
                        "results": [
                            {"target_id": "T1", "status": 200, "action": "update", "target_name": "T1"},
                        ],
                    },
                },
            },
        },
    }
    rows = _flatten_batch_copy_rows(result)
    assert len(rows) == 2
    assert rows[0]["integration_id"] == "A"
    assert rows[1]["target_id"] == "T1"


def test_publish_batch_copy_complete_notification_accepts_bundle_shape() -> None:
    result = {
        "results": {
            "scripts": {
                "results": [{"script_id": "s1", "status": "copied", "name": "Demo"}],
            },
        },
    }
    # Must not raise (would iterate dict keys as strings before fix).
    publish_batch_copy_complete_notification(
        result,
        source="src",
        target="dst",
        title="Bundle copy",
    )
