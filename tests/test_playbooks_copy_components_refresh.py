from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.playbooks.copy_components import (
    _refresh_target_playbook_binding_maps,
    copy_playbook_components_to_tenant,
)


@patch("cortex_ps_toolkit.playbooks.copy_components.ensure_playbooks_cache")
@patch("cortex_ps_toolkit.playbooks.copy_components.CachePlaybookResolver")
def test_refresh_target_playbook_binding_maps_applies_remap(
    mock_resolver_cls,
    mock_ensure_cache,
) -> None:
    target = MagicMock(slug="dst")
    mock_resolver_cls.return_value.name_to_id.return_value = {"Sub PB": "target-sub-id"}
    mock_resolver_cls.return_value.id_to_name.return_value = {"target-sub-id": "Sub PB"}

    name_to_id, id_to_name = _refresh_target_playbook_binding_maps(
        target,
        {"source-sub-id": "target-sub-id"},
        force=True,
    )

    mock_ensure_cache.assert_called_once_with(target, force=True)
    assert name_to_id["Sub PB"] == "target-sub-id"
    assert id_to_name["source-sub-id"] == "Sub PB"


@patch("cortex_ps_toolkit.playbooks.copy_components.refresh_playbooks_cache")
@patch("cortex_ps_toolkit.playbooks.copy_components.save_playbook_document")
@patch("cortex_ps_toolkit.playbooks.copy_components.api.get_playbook")
@patch("cortex_ps_toolkit.playbooks.copy_components.build_script_id_remap", return_value={})
@patch("cortex_ps_toolkit.playbooks.copy_components.ensure_scripts_cache")
@patch("cortex_ps_toolkit.playbooks.copy_components.ensure_playbooks_cache")
@patch("cortex_ps_toolkit.playbooks.copy_components.ensure_analysis_caches")
@patch("cortex_ps_toolkit.playbooks.copy_components.copy_scripts_to_tenant")
@patch("cortex_ps_toolkit.playbooks.copy_components.plan_playbook_components_copy")
@patch("cortex_ps_toolkit.playbooks.copy_components.get_profile")
def test_copy_components_refreshes_playbooks_cache_after_each_upload(
    mock_get_profile,
    mock_plan,
    mock_copy_scripts,
    mock_ensure_analysis,
    mock_ensure_playbooks,
    mock_ensure_scripts,
    mock_build_remap,
    mock_get_playbook,
    mock_save_playbook,
    mock_refresh_playbooks,
) -> None:
    source = MagicMock(slug="src", tenant_type="xsiam")
    target = MagicMock(slug="dst", tenant_type="xsiam")
    mock_get_profile.side_effect = lambda slug: source if slug == "src" else target
    mock_plan.return_value = {
        "would_abort": False,
        "missing_sub_playbooks": [],
        "root_playbook_name": "Main PB",
        "analysis_summary": {"script_ids": []},
        "scripts": {"items": []},
        "playbooks": {
            "items": [
                {"playbook_id": "sub-id", "name": "Sub PB", "action": "update", "target_id": "t-sub"},
                {"playbook_id": "root-id", "name": "Main PB", "action": "update", "target_id": "t-root"},
            ],
            "copy_order": ["sub-id", "root-id"],
        },
    }
    mock_get_playbook.side_effect = lambda profile, pb_id: {"id": pb_id, "name": "pb", "tasks": {}}
    mock_save_playbook.return_value = ({"id": "saved"}, 200, [])

    with patch(
        "cortex_ps_toolkit.playbooks.copy_components._refresh_target_playbook_binding_maps",
        side_effect=lambda _target, _remap, force=False: ({}, {}),
    ) as mock_refresh_maps:
        copy_playbook_components_to_tenant("src", "dst", "root-id", overwrite=True)

    # Initial bind refresh + one forced refresh after each uploaded playbook (sub, root).
    assert mock_refresh_maps.call_count == 3
    assert mock_refresh_maps.call_args_list[1].kwargs.get("force") is True
    assert mock_refresh_maps.call_args_list[2].kwargs.get("force") is True
