from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.platforms import Platform
from cortex_ps_toolkit.playbooks.entity_resolution import resolve_script_task_bindings
from cortex_ps_toolkit.playbooks.yaml_bindings import (
    finalize_subplaybook_fields_for_yaml,
    prepare_playbook_bindings_for_upload,
)
from cortex_ps_toolkit.playbooks.yaml_export import rename_playbook_keys_for_yaml


def test_finalize_subplaybook_xsoar_drops_playbook_id() -> None:
    playbook = {
        "tasks": {
            "1": {
                "type": "playbook",
                "task": {
                    "name": "Call sub",
                    "playbookId": "sub-id",
                    "playbookName": "Sub PB",
                },
            }
        }
    }
    finalize_subplaybook_fields_for_yaml(playbook, bind_subplaybooks_by_id=False)
    inner = playbook["tasks"]["1"]["task"]
    assert "playbookId" not in inner
    assert inner["playbookName"] == "Sub PB"


def test_finalize_subplaybook_xsiam_keeps_playbook_id() -> None:
    playbook = {
        "tasks": {
            "1": {
                "type": "playbook",
                "task": {
                    "name": "Call sub",
                    "playbookId": "sub-uuid",
                    "playbookName": "Sub PB",
                },
            }
        }
    }
    finalize_subplaybook_fields_for_yaml(playbook, bind_subplaybooks_by_id=True)
    inner = playbook["tasks"]["1"]["task"]
    assert inner["playbookId"] == "sub-uuid"
    assert inner["playbookName"] == "Sub PB"


def test_resolve_script_name_as_id_binding() -> None:
    playbook = {
        "tasks": {
            "1": {
                "type": "regular",
                "task": {"name": "Set value", "scriptId": "SetAndHandleEmpty"},
            }
        }
    }
    unresolved = resolve_script_task_bindings(
        playbook,
        id_to_name={"SetAndHandleEmpty": "SetAndHandleEmpty"},
        name_to_id={"SetAndHandleEmpty": "SetAndHandleEmpty"},
    )
    inner = playbook["tasks"]["1"]["task"]
    assert unresolved == []
    assert inner["scriptName"] == "SetAndHandleEmpty"
    assert "scriptId" not in inner


@patch("cortex_ps_toolkit.playbooks.yaml_bindings.script_index_maps")
@patch("cortex_ps_toolkit.playbooks.yaml_bindings.CachePlaybookResolver")
def test_prepare_playbook_bindings_xsoar_yaml_shape(
    mock_resolver_cls: MagicMock,
    mock_script_maps: MagicMock,
) -> None:
    profile = MagicMock()
    profile.tenant_type = Platform.XSOAR8

    mock_resolver = mock_resolver_cls.return_value
    mock_resolver.name_to_id.return_value = {"Sub PB": "sub-id"}
    mock_resolver.id_to_name.return_value = {"sub-id": "Sub PB"}
    mock_script_maps.return_value = ({}, {})

    playbook = {
        "tasks": {
            "1": {
                "type": "playbook",
                "task": {
                    "name": "Call sub",
                    "playbookId": "foreign-id",
                    "playbookName": "Sub PB",
                },
            }
        }
    }
    unresolved = prepare_playbook_bindings_for_upload(playbook, profile)
    assert unresolved == []
    yaml_ready = rename_playbook_keys_for_yaml(playbook)
    inner = yaml_ready["tasks"]["1"]["task"]
    assert "playbookid" not in inner
    assert inner["playbookName"] == "Sub PB"
