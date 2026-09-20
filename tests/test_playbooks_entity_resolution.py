from __future__ import annotations

from cortex_ps_toolkit.playbooks.bindings import resolve_playbook_task_bindings
from cortex_ps_toolkit.playbooks.entity_resolution import (
    resolve_automation_script,
    resolve_script_task_bindings,
)
from cortex_ps_toolkit.playbooks.yaml_helpers import command_display_from_task


def test_resolve_automation_script_uuid_binding() -> None:
    script_uuid = "cdbde451-2283-4ae5-8e00-9c0d16fdcf16"
    node = {
        "type": "regular",
        "task": {"name": "Http step", "script": script_uuid, "scriptName": "HttpV2"},
    }
    script_by_id = {script_uuid: {"id": script_uuid, "name": "HttpV2"}}
    ref = resolve_automation_script(node, script_by_id=script_by_id, script_by_name={})
    assert ref is not None
    assert ref.canonical_name == "HttpV2"
    assert ref.script_id == script_uuid
    assert ref.command_display == "HttpV2"
    assert ref.command_raw == script_uuid


def test_integration_command_is_not_automation_copy_scope() -> None:
    node = {
        "type": "regular",
        "task": {"name": "Set issue", "script": "Builtin|||setIssue", "isCommand": True},
    }
    assert resolve_automation_script(node, script_by_id={}, script_by_name={}) is None
    command = command_display_from_task(node, script_by_id={})
    assert command is not None
    assert command["command"] == "Builtin|||setIssue"


def test_resolve_script_task_bindings_rewrites_uuid_to_script_name() -> None:
    script_uuid = "cdbde451-2283-4ae5-8e00-9c0d16fdcf16"
    playbook = {
        "tasks": {
            "1": {
                "type": "regular",
                "task": {
                    "name": "Http step",
                    "script": script_uuid,
                    "scriptId": script_uuid,
                },
            }
        }
    }
    unresolved = resolve_script_task_bindings(
        playbook,
        id_to_name={script_uuid: "HttpV2"},
        name_to_id={"HttpV2": script_uuid},
    )
    inner = playbook["tasks"]["1"]["task"]
    assert unresolved == []
    assert inner["scriptName"] == "HttpV2"
    assert "script" not in inner
    assert "scriptId" not in inner


def test_resolve_playbook_task_bindings_prefers_name_when_id_missing_from_cache() -> None:
    playbook = {
        "tasks": {
            "2": {
                "type": "playbook",
                "task": {
                    "name": "Call sub",
                    "playbookId": "foreign-id",
                    "playbookName": "Sub PB",
                },
            }
        }
    }
    unresolved = resolve_playbook_task_bindings(
        playbook,
        name_to_id={"Sub PB": "local-sub-id"},
        id_to_name={"local-sub-id": "Sub PB"},
    )
    assert unresolved == []
    inner = playbook["tasks"]["2"]["task"]
    assert inner["playbookId"] == "local-sub-id"
    assert inner["playbookName"] == "Sub PB"
