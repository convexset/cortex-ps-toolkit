from __future__ import annotations

from cortex_ps_toolkit.content.representation import diff_representations, normalize_representation


def test_normalize_representation_script_docker_alias() -> None:
    left = normalize_representation({"id": "1", "name": "A", "dockerImage": "demisto/python3:1"}, "script")
    right = normalize_representation({"id": "2", "name": "B", "dockerimage": "demisto/python3:1"}, "script")
    assert left == right


def test_diff_representations_ignores_identity_fields() -> None:
    source = {"id": "1", "name": "A", "script": "print('x')", "type": "python", "version": 3}
    copied = {"id": "2", "name": "B", "script": "print('x')", "type": "python", "version": 1}
    diff = diff_representations(source, copied, "script")
    assert diff.equal is True


def test_normalize_representation_script_args_alias() -> None:
    left = normalize_representation({"arguments": [{"name": "x"}]}, "script")
    right = normalize_representation({"args": [{"name": "x"}]}, "script")
    assert left == right


def test_playbook_ignores_platform_envelope_fields() -> None:
    source = {"name": "PB", "tasks": {"1": {"type": "start", "task": {"name": "Start"}}}}
    copied = {
        "name": "PB",
        "adopted": True,
        "contentitemexportablefields": {"contentitemfields": {"isoverridable": False}},
        "outlinetasks": {},
        "possibleresponses": [],
        "tasks": {"1": {"type": "start", "task": {"name": "Start"}}},
    }
    diff = diff_representations(source, copied, "playbook")
    assert diff.equal is True


def test_playbook_normalizes_task_envelope_noise() -> None:
    source = {
        "name": "PB",
        "tasks": {
            "2": {
                "type": "regular",
                "continueOnErrorType": "",
                "scriptarguments": {"x": {"simple": "1"}},
                "task": {
                    "name": "Run",
                    "scriptName": "MyScript",
                    "scriptId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    "brand": "Builtin",
                    "isCommand": True,
                },
            }
        },
    }
    copied = {
        "name": "PB",
        "tasks": {
            "2": {
                "type": "regular",
                "continueonerrortype": None,
                "scriptArguments": {"x": {"simple": "1"}},
                "evidenceData": {},
                "task": {
                    "name": "Run",
                    "scriptName": "MyScript",
                    "script": "Print",
                    "playbooktaskmissingcomponent": False,
                },
            }
        },
    }
    diff = diff_representations(source, copied, "playbook")
    assert diff.equal is True


def test_script_ignores_arg_and_metadata_envelope() -> None:
    source = {
        "name": "Custom",
        "type": "python",
        "script": "return_results('ok')",
        "args": [
            {
                "name": "flag",
                "default": False,
                "deprecated": False,
                "hidden": False,
                "secret": False,
                "type": "",
            }
        ],
        "deprecated": False,
        "contextKeys": [],
        "runOnce": False,
    }
    copied = {
        "name": "Custom",
        "type": "python",
        "script": "return_results('ok')",
        "args": [{"name": "flag"}],
        "contentitemexportablefields": {"contentitemfields": {"isoverridable": False}},
        "commonfields": {},
    }
    diff = diff_representations(source, copied, "script")
    assert diff.equal is True


def test_playbook_sub_playbook_binding_by_name_only() -> None:
    source = {
        "name": "Main",
        "tasks": {"3": {"type": "playbook", "task": {"name": "Sub", "playbookName": "Child_PB"}}},
    }
    copied = {
        "name": "Main",
        "tasks": {
            "3": {
                "type": "playbook",
                "task": {
                    "name": "Sub",
                    "playbookName": "Child_PB",
                    "playbookId": "11111111-2222-3333-4444-555555555555",
                },
            }
        },
    }
    diff = diff_representations(source, copied, "playbook")
    assert diff.equal is True
