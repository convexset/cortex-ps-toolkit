from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.playbooks.graph import (
    compute_completion_path_metrics,
    compute_conditional_branches_by_task,
    compute_playbook_task_listings,
    compute_task_summaries_by_reachability,
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


@patch.object(CachePlaybookResolver, "load_by_key")
@patch.object(CachePlaybookResolver, "load")
@patch.object(CachePlaybookResolver, "resolve")
@patch.object(CachePlaybookResolver, "_build_index")
def test_completion_path_metrics_recursive(
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
    metrics = compute_completion_path_metrics(_flow_root(), resolver)

    assert metrics["min_tasks_to_completion"] is not None
    assert metrics["max_tasks_to_completion"] is not None
    assert metrics["min_tasks_to_completion"] <= metrics["max_tasks_to_completion"]
    assert metrics["terminal_count"] >= 1


@patch.object(CachePlaybookResolver, "load_by_key")
@patch.object(CachePlaybookResolver, "load")
@patch.object(CachePlaybookResolver, "resolve")
@patch.object(CachePlaybookResolver, "_build_index")
def test_task_summaries_split_reachability(
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
    reachable, unreachable, totals = compute_task_summaries_by_reachability(
        playbooks,
        _flow_root(),
        resolver,
    )

    assert totals["unreachable"] >= 1
    assert totals["reachable"] >= 1
    assert any(row["label"] == "Orphan" or "Orphan" in str(row) for row in unreachable) or totals["unreachable"] > 0
    assert all("scripts" in row and "commands" in row and "playbooks" in row for row in reachable)
    assert all("conditional_branches" not in row for row in reachable)


@patch.object(CachePlaybookResolver, "load_by_key")
@patch.object(CachePlaybookResolver, "load")
@patch.object(CachePlaybookResolver, "resolve")
@patch.object(CachePlaybookResolver, "_build_index")
def test_playbook_task_listings_include_path_metrics(
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
    listings = compute_playbook_task_listings(playbooks, _flow_root(), resolver)
    root = next(item for item in listings if item["playbook_id"] == "root-id")
    task_one = next(row for row in root["tasks"] if row["task_id"] == "1")
    assert task_one["expanded_reachable"] is True
    assert task_one["min_steps_from_start"] is not None
    assert "conditional_branches" in task_one
    orphan = next(row for row in root["tasks"] if row["task_id"] == "9")
    assert orphan["expanded_reachable"] is False


def test_conditional_branches_union_predecessor_paths() -> None:
    playbook = {
        "startTaskId": "0",
        "tasks": {
            "0": {"type": "start", "task": {"name": "Start"}, "nextTasks": {"#none#": ["1"]}},
            "1": {
                "type": "condition",
                "task": {"name": "Check"},
                "nextTasks": {"#yes#": ["2"], "#no#": ["3"]},
            },
            "2": {"type": "regular", "task": {"name": "Yes path"}, "nextTasks": {"#none#": ["4"]}},
            "3": {"type": "regular", "task": {"name": "No path"}},
            "4": {"type": "regular", "task": {"name": "After yes"}},
        },
    }
    branches = compute_conditional_branches_by_task(playbook)
    assert branches["2"] == {"yes"}
    assert branches["3"] == {"no"}
    assert branches["4"] == {"yes"}
