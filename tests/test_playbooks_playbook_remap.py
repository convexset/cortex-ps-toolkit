from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.playbooks.bindings import resolve_playbook_task_bindings
from cortex_ps_toolkit.playbooks.playbook_remap import seed_playbook_id_remap
from cortex_ps_toolkit.playbooks.yaml_bindings import prepare_playbook_bindings_for_upload
from cortex_ps_toolkit.platforms import Platform


def test_seed_playbook_id_remap_from_plan() -> None:
    items = [
        {"playbook_id": "src-sub", "name": "Sub PB", "target_id": "tgt-sub"},
        {"playbook_id": "src-root", "name": "Main PB", "action": "copy"},
    ]
    assert seed_playbook_id_remap(items) == {"src-sub": "tgt-sub"}


def test_resolve_playbook_bindings_with_remap() -> None:
    playbook = {
        "tasks": {
            "2": {
                "type": "playbook",
                "task": {
                    "name": "Call sub",
                    "playbookId": "source-sub-uuid",
                    "playbookName": "Sub PB",
                },
            }
        }
    }
    unresolved = resolve_playbook_task_bindings(
        playbook,
        name_to_id={"Sub PB": "target-sub-uuid"},
        id_to_name={"target-sub-uuid": "Sub PB"},
        playbook_id_remap={"source-sub-uuid": "target-sub-uuid"},
    )
    inner = playbook["tasks"]["2"]["task"]
    assert unresolved == []
    assert inner["playbookId"] == "target-sub-uuid"
    assert inner["playbookName"] == "Sub PB"


@patch("cortex_ps_toolkit.playbooks.yaml_bindings.script_index_maps")
@patch("cortex_ps_toolkit.playbooks.yaml_bindings.CachePlaybookResolver")
def test_prepare_bindings_xsiam_subplaybook_after_remap(
    mock_resolver_cls: MagicMock,
    mock_script_maps: MagicMock,
) -> None:
    profile = MagicMock()
    profile.tenant_type = Platform.XSIAM
    mock_resolver_cls.return_value.name_to_id.return_value = {}
    mock_resolver_cls.return_value.id_to_name.return_value = {}
    mock_script_maps.return_value = ({}, {})

    playbook = {
        "tasks": {
            "2": {
                "type": "playbook",
                "task": {
                    "name": "Call sub",
                    "playbookId": "xsoar-sub-id",
                    "playbookName": "Sub PB",
                },
            }
        }
    }
    unresolved = prepare_playbook_bindings_for_upload(
        playbook,
        profile,
        playbook_name_to_id={"Sub PB": "xsiam-sub-uuid"},
        playbook_id_to_name={"xsiam-sub-uuid": "Sub PB"},
        playbook_id_remap={"xsoar-sub-id": "xsiam-sub-uuid"},
    )
    inner = playbook["tasks"]["2"]["task"]
    assert unresolved == []
    assert inner["playbookId"] == "xsiam-sub-uuid"
    assert inner["playbookName"] == "Sub PB"
