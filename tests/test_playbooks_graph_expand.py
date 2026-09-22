"""Regression tests for expanded playbook graph expansion."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.playbooks.graph import build_expanded_graph_context
from cortex_ps_toolkit.playbooks.resolver import CachePlaybookResolver


@patch.object(CachePlaybookResolver, "load_by_key")
@patch.object(CachePlaybookResolver, "load")
@patch.object(CachePlaybookResolver, "_build_index")
def test_missing_successor_task_does_not_hang(
    mock_build_index: MagicMock,
    mock_load: MagicMock,
    mock_load_by_key: MagicMock,
) -> None:
    """Bad nextTasks refs must not cause infinite expand recursion."""
    mock_build_index.return_value = None
    root = {
        "id": "root-id",
        "name": "Main",
        "startTaskId": "0",
        "tasks": {
            "0": {"type": "start", "task": {"name": "Start"}, "nextTasks": {"#none#": ["1"]}},
            "1": {"type": "regular", "task": {"name": "Step"}, "nextTasks": {"#none#": ["missing"]}},
        },
    }
    mock_load.return_value = root
    mock_load_by_key.return_value = root

    resolver = CachePlaybookResolver(MagicMock(slug="lab"))
    ctx = build_expanded_graph_context(root, resolver)
    assert len(ctx.expanded_nodes) >= 2
