"""Tests for shared expanded graph context performance helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.playbooks.graph import (
    build_expanded_graph_context,
    compute_completion_path_metrics,
    compute_playbook_task_listings,
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
                "type": "condition",
                "task": {"name": "Branch"},
                "nextTasks": {"#yes#": ["2"], "#no#": ["3"]},
            },
            "2": {"type": "title", "task": {"name": "Yes done"}},
            "3": {"type": "title", "task": {"name": "No done"}},
        },
    }


@patch.object(CachePlaybookResolver, "load_by_key")
@patch.object(CachePlaybookResolver, "load")
@patch.object(CachePlaybookResolver, "_build_index")
def test_shared_graph_context_matches_direct_metrics(
    mock_build_index,
    mock_load,
    mock_load_by_key,
) -> None:
    mock_build_index.return_value = None
    root = _flow_root()
    mock_load.return_value = root
    mock_load_by_key.return_value = root

    resolver = CachePlaybookResolver(MagicMock(slug="lab"))
    ctx = build_expanded_graph_context(root, resolver)
    metrics = compute_completion_path_metrics(root, resolver, graph_context=ctx)
    playbooks = [{"id": "root-id", "name": "Main PB", "role": "root"}]
    listings = compute_playbook_task_listings(playbooks, root, resolver, graph_context=ctx)

    assert metrics["min_tasks_to_completion"] == 3
    assert metrics["terminal_count"] == 2
    branch_task = next(row for row in listings[0]["tasks"] if row["task_id"] == "2")
    assert branch_task["conditional_branches"] == [{"label": "yes", "condition_task_id": "1"}]
