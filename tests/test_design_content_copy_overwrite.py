"""Overwrite copy uses delete-then-recreate retry for direct incident writes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.design_content.copy import copy_assets_to_tenant


@patch("cortex_ps_toolkit.design_content.copy.refresh_asset_cache")
@patch("cortex_ps_toolkit.design_content.copy.get_item_body")
@patch("cortex_ps_toolkit.design_content.copy.execute_overwrite_write")
@patch("cortex_ps_toolkit.design_content.copy.plan_asset_copy")
@patch("cortex_ps_toolkit.design_content.copy.get_profile")
def test_incident_type_update_uses_overwrite_retry_helper(
    mock_get_profile: MagicMock,
    mock_plan: MagicMock,
    mock_execute: MagicMock,
    mock_body: MagicMock,
    mock_refresh: MagicMock,
) -> None:
    source = MagicMock(slug="src", tenant_type=MagicMock(value="xsoar6"))
    target = MagicMock(slug="dst", tenant_type=MagicMock(value="xsoar6"))
    mock_get_profile.side_effect = lambda slug: source if slug == "src" else target
    mock_plan.return_value = {
        "entries": [
            {
                "source_id": "TypeA",
                "target_id": "TypeA",
                "target_name": "TypeA",
                "action": "update",
            },
        ],
    }
    mock_body.return_value = {"id": "TypeA", "name": "TypeA", "layout": "TypeA"}
    mock_execute.return_value = (("ok", 200), {"overwrite_retry": "delete_then_create"})

    result = copy_assets_to_tenant("src", "dst", "incident-types", ["TypeA"], overwrite=True)

    assert result["executed"] is True
    mock_execute.assert_called_once()
    call_kw = mock_execute.call_args.kwargs
    assert call_kw["action"] == "update"
    assert callable(call_kw["write"])
    assert callable(call_kw["delete"])
