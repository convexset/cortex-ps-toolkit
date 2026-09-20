from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.scripts.delete import plan_scripts_delete


@patch("cortex_ps_toolkit.scripts.delete.refresh_scripts_cache")
@patch("cortex_ps_toolkit.scripts.delete.find_script_in_index")
@patch("cortex_ps_toolkit.scripts.delete.get_profile")
def test_plan_scripts_delete_blocks_system_script(
    mock_get_profile,
    mock_find,
    mock_refresh,
) -> None:
    profile = type("P", (), {"slug": "lab", "tenant_type": "xsoar8"})()
    mock_get_profile.return_value = profile
    mock_find.return_value = {"id": "sc1", "name": "Builtin", "system": True}

    plan = plan_scripts_delete("lab", ["sc1"])

    assert plan["counts"]["blocked_system"] == 1
    assert plan["items"][0]["action"] == "blocked_system"
