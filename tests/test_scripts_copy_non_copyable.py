from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.scripts.copy import plan_scripts_copy


@patch("cortex_ps_toolkit.scripts.copy.ensure_scripts_cache")
@patch("cortex_ps_toolkit.scripts.copy.find_script_in_index")
@patch("cortex_ps_toolkit.scripts.copy.resolve_script_meta")
@patch("cortex_ps_toolkit.scripts.copy.get_profile")
def test_plan_scripts_copy_blocks_system_script(
    mock_get_profile,
    mock_resolve_meta,
    mock_find_target,
    mock_ensure,
) -> None:
    source = type("P", (), {"slug": "src", "tenant_type": "xsoar8"})()
    target = type("P", (), {"slug": "dst", "tenant_type": "xsoar8"})()
    mock_get_profile.side_effect = lambda slug: source if slug == "src" else target
    mock_resolve_meta.return_value = {"id": "Print", "name": "Print", "system": True}
    mock_find_target.return_value = None

    plan = plan_scripts_copy("src", "dst", ["Print"])
    assert plan["counts"]["blocked_non_copyable"] == 1
    assert plan["items"][0]["action"] == "blocked_non_copyable"
