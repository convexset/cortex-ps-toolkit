"""Deep copy binding maps alias source names after copy-as-new upload."""

from __future__ import annotations

from unittest.mock import MagicMock

from cortex_ps_toolkit.playbooks.copy_components import _apply_playbook_remap_updates


def test_apply_playbook_remap_aliases_source_name() -> None:
    target = MagicMock(slug="lab")
    playbook_id_remap: dict[str, str] = {}
    name_to_id: dict[str, str] = {}
    id_to_name: dict[str, str] = {}
    _apply_playbook_remap_updates(
        target,
        playbook_id_remap,
        name_to_id,
        id_to_name,
        [
            {
                "source_id": "src-sub-id",
                "target_id": "tgt-sub-id",
                "name": "SubPlaybook_copy",
                "source_name": "SubPlaybook",
            },
        ],
    )
    assert name_to_id["SubPlaybook_copy"] == "tgt-sub-id"
    assert name_to_id["SubPlaybook"] == "tgt-sub-id"
