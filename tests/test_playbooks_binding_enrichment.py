from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.playbooks.binding_enrichment import enrich_bindings_from_source_cache
from cortex_ps_toolkit.playbooks.yaml_bindings import prepare_playbook_bindings_for_upload
from cortex_ps_toolkit.platforms import Platform


def test_enrich_playbook_name_from_source_cache() -> None:
    playbook = {
        "tasks": {
            "4": {
                "type": "playbook",
                "task": {
                    "name": "Call sub",
                    "playbookId": "7de7eb6f-b04b-47b0-8540-083ad3be6e8e",
                },
            }
        }
    }
    source = MagicMock()
    source.slug = "personal-xsoar6"

    with patch(
        "cortex_ps_toolkit.playbooks.binding_enrichment.CachePlaybookResolver",
    ) as mock_resolver_cls:
        mock_resolver_cls.return_value.id_to_name.return_value = {
            "7de7eb6f-b04b-47b0-8540-083ad3be6e8e": "Test_PB_Inv_Data_Unexpanded_Sub",
        }
        enrich_bindings_from_source_cache(playbook, source)

    inner = playbook["tasks"]["4"]["task"]
    assert inner["playbookName"] == "Test_PB_Inv_Data_Unexpanded_Sub"


def test_enrich_script_name_from_source_cache() -> None:
    playbook = {
        "tasks": {
            "1": {
                "type": "regular",
                "task": {
                    "name": "Show env",
                    "scriptId": "e487dee9-c2ff-46b4-8794-33fbefd2b48b",
                },
            }
        }
    }
    source = MagicMock()
    source.slug = "personal-xsoar6"

    with patch(
        "cortex_ps_toolkit.playbooks.binding_enrichment.script_index_maps",
        return_value=(
            {
                "e487dee9-c2ff-46b4-8794-33fbefd2b48b": {
                    "id": "e487dee9-c2ff-46b4-8794-33fbefd2b48b",
                    "name": "TEST_Show_Env",
                }
            },
            {},
        ),
    ):
        enrich_bindings_from_source_cache(playbook, source)

    inner = playbook["tasks"]["1"]["task"]
    assert inner["scriptName"] == "TEST_Show_Env"


@patch("cortex_ps_toolkit.playbooks.yaml_bindings.enrich_bindings_from_source_cache")
@patch("cortex_ps_toolkit.playbooks.yaml_bindings.script_index_maps")
@patch("cortex_ps_toolkit.playbooks.yaml_bindings.CachePlaybookResolver")
def test_prepare_bindings_enriches_from_source_then_binds_on_target(
    mock_resolver_cls: MagicMock,
    mock_script_maps: MagicMock,
    mock_enrich: MagicMock,
) -> None:
    target = MagicMock()
    target.tenant_type = Platform.XSIAM
    source = MagicMock()
    source.slug = "personal-xsoar6"

    def _enrich(playbook: dict, _source: MagicMock) -> None:
        playbook["tasks"]["4"]["task"]["playbookName"] = "Test_PB_Inv_Data_Unexpanded_Sub"

    mock_enrich.side_effect = _enrich
    mock_script_maps.return_value = ({}, {})
    mock_resolver_cls.return_value.name_to_id.return_value = {
        "Test_PB_Inv_Data_Unexpanded_Sub": "xsiam-sub-uuid",
    }
    mock_resolver_cls.return_value.id_to_name.return_value = {
        "xsiam-sub-uuid": "Test_PB_Inv_Data_Unexpanded_Sub",
    }

    playbook = {
        "tasks": {
            "4": {
                "type": "playbook",
                "task": {
                    "name": "Call sub",
                    "playbookId": "7de7eb6f-b04b-47b0-8540-083ad3be6e8e",
                },
            }
        }
    }
    unresolved = prepare_playbook_bindings_for_upload(
        playbook,
        target,
        source_profile=source,
    )
    mock_enrich.assert_called_once_with(playbook, source)
    inner = playbook["tasks"]["4"]["task"]
    assert unresolved == []
    assert inner["playbookId"] == "xsiam-sub-uuid"
    assert inner["playbookName"] == "Test_PB_Inv_Data_Unexpanded_Sub"
