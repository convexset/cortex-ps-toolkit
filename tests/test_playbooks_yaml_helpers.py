from __future__ import annotations

from cortex_ps_toolkit.playbooks.yaml_helpers import (
    command_display_from_task,
    resolve_script_binding,
    script_label,
)


def test_resolve_script_binding_uuid_to_name() -> None:
    script_by_id = {"cdbde451-2283-4ae5-8e00-9c0d16fdcf16": {"id": "cdbde451-2283-4ae5-8e00-9c0d16fdcf16", "name": "HttpV2"}}
    display, raw = resolve_script_binding(
        "cdbde451-2283-4ae5-8e00-9c0d16fdcf16",
        script_by_id=script_by_id,
    )
    assert display == "HttpV2"
    assert raw == "cdbde451-2283-4ae5-8e00-9c0d16fdcf16"


def test_command_display_from_task_uses_script_name_hint() -> None:
    node = {
        "type": "regular",
        "task": {
            "name": "Send request",
            "scriptName": "HttpV2",
            "script": "cdbde451-2283-4ae5-8e00-9c0d16fdcf16",
        },
    }
    info = command_display_from_task(node, script_by_id={})
    assert info is not None
    assert info["command"] == "HttpV2"
    assert info["raw"] == "cdbde451-2283-4ae5-8e00-9c0d16fdcf16"
    assert info["resolved"] is True


def test_script_label_resolves_brand_uuid_in_binding() -> None:
    node = {
        "type": "regular",
        "task": {
            "script": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee|||run",
            "scriptName": "CustomPrint",
        },
    }
    script_by_id = {"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee": {"name": "CustomPrint"}}
    assert script_label(node, script_by_id=script_by_id) == "CustomPrint|||run"
