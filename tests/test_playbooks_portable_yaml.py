"""Portable playbook YAML for bundle export / manual XSOAR 6 import."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import yaml

from cortex_ps_toolkit.playbooks.portable_yaml import build_portable_playbook_yaml


@patch("cortex_ps_toolkit.playbooks.portable_yaml.api.get_playbook")
@patch("cortex_ps_toolkit.playbooks.portable_yaml.prepare_playbook_bindings_for_upload")
def test_build_portable_playbook_yaml_stringifies_view(
    mock_bindings: MagicMock,
    mock_get: MagicMock,
) -> None:
    mock_bindings.return_value = []
    mock_get.return_value = {
        "id": "pb-1",
        "name": "Test_PB",
        "version": 3,
        "cacheVersn": 1,
        "view": {"linkLabelsPosition": {}, "paper": {"dimensions": {"height": 100, "width": 200}}},
        "tasks": {
            "0": {
                "id": "0",
                "taskId": "task-uuid",
                "type": "start",
                "task": {"id": "inner-uuid", "version": 2, "name": "Start"},
                "view": {"position": {"x": 10, "y": 20}},
            },
            "1": {
                "type": "playbook",
                "task": {
                    "name": "Call sub",
                    "playbookId": "sub-uuid-from-xsoar8",
                    "playbookName": "Test_PB_Inv_Data_Unexpanded_Sub",
                },
            },
        },
    }
    profile = MagicMock()
    text = build_portable_playbook_yaml(profile, "pb-1")
    doc = yaml.safe_load(text)
    assert doc["version"] == -1
    assert isinstance(doc["view"], str)
    assert json.loads(doc["view"])["paper"]["dimensions"]["width"] == 200
    start = doc["tasks"]["0"]
    assert isinstance(start["view"], str)
    sub_inner = doc["tasks"]["1"]["task"]
    assert sub_inner["playbookName"] == "Test_PB_Inv_Data_Unexpanded_Sub"
    assert "playbookid" not in {k.lower() for k in sub_inner}
    assert "cacheversn" not in {k.lower() for k in doc}
