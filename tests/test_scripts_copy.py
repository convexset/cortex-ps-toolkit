from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.scripts.copy import copy_scripts_to_tenant, plan_scripts_copy


@patch("cortex_ps_toolkit.scripts.copy.ensure_scripts_cache")
@patch("cortex_ps_toolkit.scripts.copy.find_script_in_index")
@patch("cortex_ps_toolkit.scripts.copy.resolve_script_meta")
@patch("cortex_ps_toolkit.scripts.copy.get_profile")
def test_plan_scripts_copy_skip(
    mock_get_profile,
    mock_resolve_meta,
    mock_find_target,
    mock_ensure,
) -> None:
    source = type("P", (), {"slug": "src", "tenant_type": "xsoar8"})()
    target = type("P", (), {"slug": "dst", "tenant_type": "xsoar8"})()
    mock_get_profile.side_effect = lambda slug: source if slug == "src" else target
    mock_resolve_meta.return_value = {
        "id": "cdbde451-2283-4ae5-8e00-9c0d16fdcf16",
        "name": "PrintDebug",
    }
    mock_find_target.return_value = {"id": "existing", "name": "PrintDebug"}

    plan = plan_scripts_copy("src", "dst", ["cdbde451-2283-4ae5-8e00-9c0d16fdcf16"])
    assert plan["counts"]["skip"] == 1


@patch("cortex_ps_toolkit.scripts.copy.save_script_document")
@patch("cortex_ps_toolkit.scripts.copy.api.get_script")
@patch("cortex_ps_toolkit.scripts.copy.refresh_scripts_cache")
@patch("cortex_ps_toolkit.scripts.copy.ensure_scripts_cache")
@patch("cortex_ps_toolkit.scripts.copy.find_script_in_index")
@patch("cortex_ps_toolkit.scripts.copy.resolve_script_meta")
@patch("cortex_ps_toolkit.scripts.copy.get_profile")
def test_copy_scripts_to_tenant(
    mock_get_profile,
    mock_resolve_meta,
    mock_find_target,
    mock_ensure,
    mock_refresh,
    mock_get_script,
    mock_save_document,
) -> None:
    mock_refresh.return_value = {"profile": "dst"}
    source = type("P", (), {"slug": "src", "tenant_type": "xsoar8"})()
    target = type("P", (), {"slug": "dst", "tenant_type": "xsoar8"})()
    mock_get_profile.side_effect = lambda slug: source if slug == "src" else target
    mock_resolve_meta.return_value = {
        "id": "cdbde451-2283-4ae5-8e00-9c0d16fdcf16",
        "name": "PrintDebug",
    }
    mock_find_target.return_value = None
    mock_get_script.return_value = {
        "id": "cdbde451-2283-4ae5-8e00-9c0d16fdcf16",
        "name": "PrintDebug",
        "script": "print('hi')",
        "dockerImage": "demisto/python3:1.2.3",
    }
    mock_save_document.return_value = ({"id": "new-id"}, 200)

    result = copy_scripts_to_tenant(
        "src",
        "dst",
        ["cdbde451-2283-4ae5-8e00-9c0d16fdcf16"],
        overwrite=True,
    )
    assert result["results"][0]["status"] == "copied"
    mock_save_document.assert_called_once()
