"""Unit tests for cross-tenant design content orchestrator."""

from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.design_content.orchestrator import execute_cross_tenant_workflow


@patch("cortex_ps_toolkit.design_content.orchestrator.copy_assets_to_tenant")
@patch("cortex_ps_toolkit.design_content.orchestrator.get_profile")
def test_orchestrator_runs_assets_in_order(mock_get_profile, mock_copy) -> None:
    source = type("P", (), {"slug": "src"})()
    target = type("P", (), {"slug": "tgt"})()
    mock_get_profile.side_effect = [source, target]
    mock_copy.return_value = {"executed": True, "results": []}

    result = execute_cross_tenant_workflow(
        "src",
        "tgt",
        {"incident-fields": ["field_a"], "layouts": ["layout_a"]},
    )

    assert result["executed"] is True
    assert mock_copy.call_count == 2
    assets = [call.args[2] for call in mock_copy.call_args_list]
    assert assets[0] == "incident-fields"
    assert assets[1] == "layouts"
