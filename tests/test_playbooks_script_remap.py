from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.playbooks.script_remap import build_script_id_remap
from cortex_ps_toolkit.playbooks.yaml_bindings import (
    finalize_script_fields_for_yaml,
    prepare_playbook_bindings_for_upload,
)
from cortex_ps_toolkit.platforms import Platform


def test_build_script_id_remap_from_copy_results() -> None:
    target = MagicMock()
    target.slug = "dst"
    plan_items = [
        {"script_id": "src-1", "name": "HttpV2", "target_id": "tgt-existing"},
        {"script_id": "src-2", "name": "PrintDebug"},
    ]
    script_results = [
        {"script_id": "src-1", "status": "skipped", "target_script_id": "tgt-existing"},
        {"script_id": "src-2", "status": "copied", "target_script_id": "tgt-new"},
    ]
    remap = build_script_id_remap(plan_items, script_results, target)
    assert remap == {"src-1": "tgt-existing", "src-2": "tgt-new"}


def test_prepare_bindings_uses_script_remap_for_source_uuid() -> None:
    profile = MagicMock()
    profile.tenant_type = Platform.XSIAM

    playbook = {
        "tasks": {
            "1": {
                "type": "regular",
                "task": {
                    "name": "Http step",
                    "scriptId": "source-script-uuid",
                    "script": "source-script-uuid",
                },
            }
        }
    }

    with (
        patch(
            "cortex_ps_toolkit.playbooks.yaml_bindings.script_index_maps",
            return_value=(
                {"target-script-uuid": {"id": "target-script-uuid", "name": "HttpV2"}},
                {"HttpV2": {"id": "target-script-uuid", "name": "HttpV2"}},
            ),
        ),
        patch(
            "cortex_ps_toolkit.playbooks.yaml_bindings.CachePlaybookResolver",
        ) as mock_resolver_cls,
    ):
        mock_resolver_cls.return_value.name_to_id.return_value = {}
        mock_resolver_cls.return_value.id_to_name.return_value = {}
        unresolved = prepare_playbook_bindings_for_upload(
            playbook,
            profile,
            script_id_remap={"source-script-uuid": "target-script-uuid"},
        )

    inner = playbook["tasks"]["1"]["task"]
    assert unresolved == []
    assert inner["scriptName"] == "HttpV2"
    assert inner["scriptId"] == "target-script-uuid"


def test_finalize_script_fields_for_yaml_xsoar_skips_script_id() -> None:
    playbook = {
        "tasks": {
            "1": {
                "type": "regular",
                "task": {"scriptName": "HttpV2"},
            }
        }
    }
    finalize_script_fields_for_yaml(
        playbook,
        bind_scripts_by_id=False,
        name_to_id={"HttpV2": "target-id"},
    )
    assert "scriptId" not in playbook["tasks"]["1"]["task"]
