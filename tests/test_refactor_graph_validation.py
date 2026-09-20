from __future__ import annotations

import pytest

pytest.importorskip("playbook_utils.graph")

from cortex_ps_toolkit.playbooks.refactor_graph_validation import (
    build_refactor_task_catalog,
    validate_cluster_extract,
    validate_leaf_extract,
)


MINI_PLAYBOOK = {
    "tasks": {
        "0": {"id": "0", "type": "start", "task": {"name": "Start"}, "nextTasks": {"#none#": ["1"]}},
        "1": {
            "id": "1",
            "type": "regular",
            "task": {"name": "Step A", "scriptName": "Print"},
            "nextTasks": {"#none#": ["2"]},
        },
        "2": {
            "id": "2",
            "type": "regular",
            "task": {"name": "Step B", "scriptName": "Print"},
            "nextTasks": {},
        },
    },
    "starttaskid": "0",
}


def test_build_refactor_task_catalog_marks_leaf_candidates() -> None:
    catalog = build_refactor_task_catalog(MINI_PLAYBOOK)
    by_id = {row["id"]: row for row in catalog}
    assert "0" not in by_id
    assert by_id["2"]["leaf_ok"] is True
    assert by_id["1"]["leaf_ok"] is False


def test_validate_cluster_extract_accepts_simple_range() -> None:
    result = validate_cluster_extract(MINI_PLAYBOOK, "1", "2")
    assert result["ok"] is True
    assert result["cluster_task_ids"]


def test_validate_leaf_extract_rejects_non_root() -> None:
    result = validate_leaf_extract(MINI_PLAYBOOK, "1")
    assert result["ok"] is False
    assert result["reasons"]


def test_validate_leaf_extract_accepts_terminal_task() -> None:
    result = validate_leaf_extract(MINI_PLAYBOOK, "2")
    assert result["ok"] is True
    assert not result["reasons"]


def test_build_refactor_task_catalog_includes_description_fields() -> None:
    catalog = build_refactor_task_catalog(MINI_PLAYBOOK)
    assert all("description" in row and "description_short" in row for row in catalog)
