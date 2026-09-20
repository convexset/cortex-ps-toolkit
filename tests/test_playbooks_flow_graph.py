from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.playbooks.flow_graph import (
    build_flow_graphs_for_tree,
    build_playbook_flow_graph,
)
from cortex_ps_toolkit.playbooks.resolver import CachePlaybookResolver


def _flow_root() -> dict:
    return {
        "id": "root-id",
        "name": "Main PB",
        "startTaskId": "0",
        "tasks": {
            "0": {"type": "start", "task": {"name": "Start"}, "nextTasks": {"#none#": ["1"]}},
            "1": {
                "type": "regular",
                "task": {"name": "Http step", "scriptName": "HttpV2"},
                "nextTasks": {"#none#": ["2"]},
            },
            "2": {
                "type": "playbook",
                "task": {"name": "Call sub", "playbookId": "sub-id", "playbookName": "Sub PB"},
                "nextTasks": {"#none#": ["3"]},
            },
            "3": {"type": "title", "task": {"name": "Done"}},
            "9": {"type": "regular", "task": {"name": "Orphan"}},
        },
    }


def _flow_sub() -> dict:
    return {
        "id": "sub-id",
        "name": "Sub PB",
        "startTaskId": "0",
        "tasks": {
            "0": {"type": "start", "task": {"name": "Start"}, "nextTasks": {"#none#": ["1"]}},
            "1": {"type": "regular", "task": {"name": "Print", "scriptName": "Print"}},
        },
    }


def test_build_playbook_flow_graph_edges_and_conditions() -> None:
    graph = build_playbook_flow_graph(_flow_root(), script_by_id={}, script_by_name={})
    assert graph["start_task_id"] == "0"
    assert any(node["id"] == "2" and node["task_type"] == "playbook" for node in graph["nodes"])
    assert any(edge["from"] == "1" and edge["to"] == "2" and edge["condition"] == "" for edge in graph["edges"])
    sub_node = next(node for node in graph["nodes"] if node["id"] == "2")
    assert sub_node["playbook_name"] == "Sub PB"
    assert sub_node["playbook_id"] == "sub-id"
    script_node = next(node for node in graph["nodes"] if node["id"] == "1")
    assert script_node["script_name"] == "HttpV2"
    start_node = next(node for node in graph["nodes"] if node["id"] == "0")
    assert start_node["is_start"] is True
    assert start_node["raw_task"]["type"] == "start"
    assert "nexttasks" in start_node["raw_task_yaml"] or "nextTasks" in start_node["raw_task_yaml"]


def test_build_playbook_flow_graph_labeled_branch() -> None:
    playbook = {
        "startTaskId": "1",
        "tasks": {
            "1": {"type": "condition", "task": {"name": "Check"}, "nextTasks": {"yes": ["2"], "no": ["3"]}},
            "2": {"type": "title", "task": {"name": "Yes path"}},
            "3": {"type": "title", "task": {"name": "No path"}},
        },
    }
    graph = build_playbook_flow_graph(playbook, script_by_id={}, script_by_name={})
    assert any(edge["from"] == "1" and edge["to"] == "2" and edge["condition"] == "yes" for edge in graph["edges"])
    assert any(edge["from"] == "1" and edge["to"] == "3" and edge["condition"] == "no" for edge in graph["edges"])


def test_build_playbook_flow_graph_default_branch_labeled_else() -> None:
    playbook = {
        "startTaskId": "1",
        "tasks": {
            "1": {
                "type": "condition",
                "task": {"name": "Check Result"},
                "nextTasks": {"SPFpass": ["2"], "#default#": ["3"]},
            },
            "2": {"type": "title", "task": {"name": "Pass path"}},
            "3": {"type": "title", "task": {"name": "Else path"}},
        },
    }
    graph = build_playbook_flow_graph(playbook, script_by_id={}, script_by_name={})
    assert any(
        edge["from"] == "1" and edge["to"] == "3" and edge["condition"] == "ELSE"
        for edge in graph["edges"]
    )


@patch.object(CachePlaybookResolver, "load_by_key")
@patch.object(CachePlaybookResolver, "load")
@patch.object(CachePlaybookResolver, "resolve")
@patch.object(CachePlaybookResolver, "_build_index")
def test_build_flow_graphs_for_tree(
    mock_build_index,
    mock_resolve,
    mock_load,
    mock_load_by_key,
) -> None:
    mock_build_index.return_value = None
    mock_resolve.side_effect = lambda pid, pname: "sub-id" if (pid == "sub-id" or pname == "Sub PB") else None
    mock_load.side_effect = lambda pb_id: _flow_sub() if pb_id == "sub-id" else _flow_root()
    mock_load_by_key.side_effect = lambda key: _flow_sub() if key == "sub-id" else _flow_root()

    resolver = CachePlaybookResolver(MagicMock(slug="lab"))
    playbooks = [
        {"id": "root-id", "name": "Main PB", "role": "root"},
        {"id": "sub-id", "name": "Sub PB", "role": "sub_playbook"},
    ]
    graphs = build_flow_graphs_for_tree(
        playbooks,
        _flow_root(),
        resolver,
        script_by_id={},
        script_by_name={},
    )
    assert len(graphs) == 2
    assert graphs[0]["role"] == "root"
    assert graphs[0]["graph"]["nodes"]
    orphan = next(node for node in graphs[0]["graph"]["nodes"] if node["id"] == "9")
    assert orphan["reachable"] is False
