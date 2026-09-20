from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.playbooks.analysis import (
    _build_notes,
    analyze_playbook,
    build_structure_graph,
    build_structure_tree_lines,
)
from cortex_ps_toolkit.playbooks.resolver import CachePlaybookResolver


def _sample_root() -> dict:
    return {
        "id": "root-id",
        "name": "Main PB",
        "tasks": {
            "0": {"type": "start", "task": {"name": "Start"}},
            "1": {
                "type": "regular",
                "task": {"name": "Http step", "scriptName": "HttpV2", "script": "HttpV2|||send"},
            },
            "2": {
                "type": "playbook",
                "task": {"name": "Call sub", "playbookId": "sub-id", "playbookName": "Sub PB"},
            },
        },
    }


def _sample_sub() -> dict:
    return {
        "id": "sub-id",
        "name": "Sub PB",
        "tasks": {
            "0": {"type": "start", "task": {"name": "Start"}},
            "1": {
                "type": "regular",
                "task": {"name": "Print", "scriptName": "Print", "script": "Print|||"},
            },
        },
    }


@patch.object(CachePlaybookResolver, "load")
@patch.object(CachePlaybookResolver, "resolve")
@patch.object(CachePlaybookResolver, "_build_index")
def test_build_structure_tree_lines(mock_build_index, mock_resolve, mock_load) -> None:
    mock_build_index.return_value = None
    mock_resolve.side_effect = lambda pid, pname: "sub-id" if (pid == "sub-id" or pname == "Sub PB") else None
    mock_load.side_effect = lambda pb_id: _sample_sub() if pb_id == "sub-id" else _sample_root()

    resolver = CachePlaybookResolver(MagicMock(slug="lab"))
    lines = build_structure_tree_lines(_sample_root(), resolver)
    assert lines[0] == "Main PB"
    assert any("Sub PB" in line for line in lines)


@patch.object(CachePlaybookResolver, "load")
@patch.object(CachePlaybookResolver, "resolve")
@patch.object(CachePlaybookResolver, "_build_index")
def test_build_structure_graph(mock_build_index, mock_resolve, mock_load) -> None:
    mock_build_index.return_value = None
    mock_resolve.side_effect = lambda pid, pname: "sub-id" if (pid == "sub-id" or pname == "Sub PB") else None
    mock_load.side_effect = lambda pb_id: _sample_sub() if pb_id == "sub-id" else _sample_root()

    resolver = CachePlaybookResolver(MagicMock(slug="lab"))
    graph = build_structure_graph(_sample_root(), resolver)
    assert graph["nodes"][0]["name"] == "Main PB"
    assert any(node["name"] == "Sub PB" for node in graph["nodes"])
    assert graph["edges"]
    assert graph["edges"][0]["from"] == graph["nodes"][0]["id"]


@patch("cortex_ps_toolkit.playbooks.analysis.ensure_analysis_caches")
@patch("cortex_ps_toolkit.playbooks.analysis.script_index_maps")
@patch("cortex_ps_toolkit.playbooks.analysis.find_script_in_index")
@patch.object(CachePlaybookResolver, "load")
@patch.object(CachePlaybookResolver, "resolve")
@patch.object(CachePlaybookResolver, "_build_index")
@patch("cortex_ps_toolkit.playbooks.analysis.get_profile")
def test_analyze_playbook_collects_scripts_and_subs(
    mock_get_profile,
    mock_build_index,
    mock_resolve,
    mock_load,
    mock_find_script,
    mock_script_maps,
    mock_ensure,
) -> None:
    mock_get_profile.return_value = MagicMock(slug="lab")
    mock_build_index.return_value = None
    mock_resolve.side_effect = lambda pid, pname: "sub-id" if (pid == "sub-id" or pname == "Sub PB") else None
    mock_load.side_effect = lambda pb_id: _sample_sub() if pb_id == "sub-id" else _sample_root()
    http_script_id = "cdbde451-2283-4ae5-8e00-9c0d16fdcf16"
    mock_script_maps.return_value = (
        {},
        {
            "HttpV2": {"id": http_script_id, "name": "HttpV2"},
            "Print": {"id": "Print", "name": "Print", "system": True},
        },
    )
    mock_find_script.side_effect = lambda profile, name=None, script_id=None: (
        {"id": http_script_id, "name": name}
        if name == "HttpV2"
        else {"id": "Print", "name": "Print", "system": True}
        if name == "Print" or script_id == "Print"
        else None
    )

    result = analyze_playbook("lab", "root-id")
    assert result["root_playbook"]["name"] == "Main PB"
    assert result["copy_scope"]["playbook_count"] == 2
    assert any(row["name"] == "HttpV2" for row in result["scripts_used"])
    commands = result.get("integration_commands_used") or result.get("commands_used") or []
    assert any(row["command"].startswith("HttpV2") for row in commands)
    assert result["playbook_occurrences"]["Sub PB"] == 1
    assert "task_summary_reachable" in result
    assert "task_summary_unreachable" in result
    assert "completion_paths" in result
    assert isinstance(result["notes"], list)
    assert result["copy_scope"]["script_count"] == 1
    assert result["copy_scope"]["excluded_script_count"] == 1


def test_build_notes_includes_warnings_and_info() -> None:
    notes = _build_notes(
        missing_sub_playbooks=[
            {
                "lookup_key": "Missing Sub",
                "referenced_from": "Main PB",
                "example_task_id": "2",
                "example_task_label": "Call sub",
            }
        ],
        unresolved_scripts=[
            {"name": "Print", "count": 1, "playbooks": ["Sub PB"]},
        ],
        completion_paths={
            "min_tasks_to_completion": 3,
            "max_tasks_to_completion": 5,
            "terminal_count": 2,
            "note": None,
        },
        task_reachability_totals={"reachable": 2, "unreachable": 1, "total": 3},
        structure_tree=["Main PB", "    +- Sub PB"],
        playbooks_in_tree=[
            {"id": "root-id", "name": "Main PB", "role": "root"},
            {"id": "sub-id", "name": "Sub PB", "role": "sub_playbook"},
        ],
    )
    levels = {note["level"] for note in notes}
    messages = " ".join(note["message"] for note in notes)
    assert "warning" in levels
    assert "info" in levels
    assert "Missing Sub" in messages
    assert "Print" in messages
    assert "unreachable" in messages


@patch("cortex_ps_toolkit.playbooks.analysis.ensure_analysis_caches")
@patch("cortex_ps_toolkit.playbooks.analysis.script_index_maps")
@patch("cortex_ps_toolkit.playbooks.analysis.find_script_in_index")
@patch.object(CachePlaybookResolver, "load")
@patch.object(CachePlaybookResolver, "resolve")
@patch.object(CachePlaybookResolver, "_build_index")
@patch("cortex_ps_toolkit.playbooks.analysis.get_profile")
def test_analyze_playbook_resolves_uuid_commands(
    mock_get_profile,
    mock_build_index,
    mock_resolve,
    mock_load,
    mock_find_script,
    mock_script_maps,
    mock_ensure,
) -> None:
    script_uuid = "cdbde451-2283-4ae5-8e00-9c0d16fdcf16"
    mock_get_profile.return_value = MagicMock(slug="lab")
    mock_build_index.return_value = None
    mock_resolve.return_value = None
    mock_script_maps.return_value = ({script_uuid: {"id": script_uuid, "name": "HttpV2"}}, {})
    mock_load.return_value = {
        "id": "root-id",
        "name": "Main PB",
        "startTaskId": "0",
        "tasks": {
            "0": {"type": "start", "task": {"name": "Start"}, "nextTasks": {"#none#": ["1"]}},
            "1": {
                "type": "regular",
                "task": {"name": "Http step", "script": script_uuid},
            },
        },
    }
    mock_find_script.return_value = None

    result = analyze_playbook("lab", "root-id")
    script_row = next(row for row in result["scripts_used"] if row["name"] == "HttpV2")
    assert script_row["script_id"] == script_uuid
    assert (result.get("integration_commands_used") or result.get("commands_used") or []) == []
