from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.playbooks.copy_components import plan_playbook_components_copy


@patch("cortex_ps_toolkit.playbooks.copy_components.ensure_scripts_cache")
@patch("cortex_ps_toolkit.playbooks.copy_components.ensure_playbooks_cache")
@patch("cortex_ps_toolkit.playbooks.copy_components.ensure_analysis_caches")
@patch("cortex_ps_toolkit.playbooks.copy_components.plan_scripts_copy")
@patch("cortex_ps_toolkit.playbooks.copy_components.analyze_playbook")
@patch("cortex_ps_toolkit.playbooks.copy_components.get_profile")
def test_plan_playbook_components_copy(
    mock_get_profile,
    mock_analyze,
    mock_plan_scripts,
    mock_ensure_pb,
    mock_ensure_scripts,
    mock_ensure_analysis,
) -> None:
    source = type("P", (), {"slug": "src", "tenant_type": "xsoar6"})()
    target = type("P", (), {"slug": "dst", "tenant_type": "xsoar6"})()
    mock_get_profile.side_effect = lambda slug: source if slug == "src" else target
    mock_analyze.return_value = {
        "profile": "src",
        "root_playbook": {"id": "root-id", "name": "Main PB"},
        "playbooks_in_tree": [
            {"id": "root-id", "name": "Main PB", "role": "root"},
            {"id": "sub-id", "name": "Sub PB", "role": "sub_playbook"},
        ],
        "copy_scope": {
            "playbook_ids": ["root-id", "sub-id"],
            "script_ids": ["script-1"],
            "playbook_count": 2,
            "script_count": 1,
            "missing_sub_playbook_count": 0,
            "unresolved_script_count": 0,
        },
        "warnings": [],
        "missing_sub_playbooks": [],
        "unresolved_scripts": [],
    }
    mock_plan_scripts.return_value = {
        "items": [{"script_id": "script-1", "name": "HttpV2", "action": "copy"}],
        "counts": {"total": 1, "copy": 1, "update": 0, "skip": 0, "conflict": 0},
        "would_abort": False,
        "conflicts": [],
    }

    sample_root = {
        "id": "root-id",
        "name": "Main PB",
        "tasks": {
            "2": {
                "type": "playbook",
                "task": {"playbookId": "sub-id", "playbookName": "Sub PB"},
            }
        },
    }
    sample_sub = {"id": "sub-id", "name": "Sub PB", "tasks": {}}

    mock_resolver = type("R", (), {})()
    mock_resolver.load = lambda pb_id: sample_sub if pb_id == "sub-id" else sample_root

    with patch(
        "cortex_ps_toolkit.playbooks.copy_components.CachePlaybookResolver",
        return_value=mock_resolver,
    ), patch(
        "cortex_ps_toolkit.playbooks.copy_components.resolve_playbook_meta",
    ) as mock_resolve_meta, patch(
        "cortex_ps_toolkit.playbooks.copy_components.find_playbook_in_index",
        return_value=None,
    ):
        mock_resolve_meta.side_effect = lambda profile, pb_id: {
            "id": pb_id,
            "name": "Main PB" if pb_id == "root-id" else "Sub PB",
        }
        plan = plan_playbook_components_copy("src", "dst", "root-id")

    assert plan["analysis_summary"]["playbook_count"] == 2
    assert plan["scripts"]["counts"]["copy"] == 1
    assert len(plan["playbooks"]["items"]) == 2
    assert plan["playbooks"]["copy_order"][-1] == "root-id"
