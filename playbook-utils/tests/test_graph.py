from __future__ import annotations

from typing import Dict

from playbook_utils.graph import check_potential_root, descendant_ids


def make_playbook() -> Dict:
    return {
        "id": "pb-main",
        "name": "Main",
        "startTaskId": "0",
        "tasks": {
            "0": {
                "id": "0",
                "type": "start",
                "task": {"name": "", "type": "start"},
                "nextTasks": {"#none#": ["1"]},
                "view": {"position": {"x": 50, "y": 0}},
            },
            "1": {
                "id": "1",
                "type": "regular",
                "task": {"name": "Alpha", "scriptId": "s-alpha", "type": "regular"},
                "nextTasks": {"#none#": ["2"]},
                "view": {"position": {"x": 50, "y": 100}},
            },
            "2": {
                "id": "2",
                "type": "condition",
                "task": {"name": "Branch", "type": "condition"},
                "nextTasks": {"yes": ["3"], "no": ["4"]},
                "conditions": [{"label": "yes", "condition": []}],
                "view": {"position": {"x": 50, "y": 200}},
            },
            "3": {
                "id": "3",
                "type": "regular",
                "task": {"name": "YesPath", "type": "regular"},
                "view": {"position": {"x": 0, "y": 300}},
            },
            "4": {
                "id": "4",
                "type": "regular",
                "task": {"name": "NoPath", "type": "regular"},
                "nextTasks": {"#none#": ["3"]},
                "view": {"position": {"x": 200, "y": 300}},
            },
        },
    }


def test_descendants_include_root_and_follow_all_branches() -> None:
    pb = make_playbook()
    assert descendant_ids(pb, "1") == ["1", "2", "4", "3"]
    assert descendant_ids(pb, "2") == ["2", "4", "3"]
    assert descendant_ids(pb, "3") == ["3"]


def test_potential_root_allows_outside_edges_only_into_root() -> None:
    pb = make_playbook()
    result = check_potential_root(pb, "1")
    assert result.ok
    assert not result.self_reachable
    assert result.incoming_to_root[0].source_id == "0"
    assert result.incoming_to_root[0].target_id == "1"


def test_potential_root_fails_when_task_can_reach_itself() -> None:
    pb = make_playbook()
    pb["tasks"]["4"]["nextTasks"] = {"#none#": ["2"]}
    result = check_potential_root(pb, "2")
    assert not result.ok
    assert result.self_reachable


def test_potential_root_allows_cycles_among_descendants() -> None:
    pb = make_playbook()
    pb["tasks"]["4"]["nextTasks"] = {"#none#": ["2"]}
    result = check_potential_root(pb, "1")
    assert result.ok
    assert not result.self_reachable
    assert set(result.descendant_ids) == {"1", "2", "3", "4"}


def test_potential_root_fails_on_outside_edge_into_descendant() -> None:
    pb = make_playbook()
    pb["tasks"]["0"]["nextTasks"] = {"#none#": ["1", "3"]}
    result = check_potential_root(pb, "1")
    assert not result.ok
    assert result.outside_incoming_to_descendants
    assert result.outside_incoming_to_descendants[0].target_id == "3"


def test_missing_task_is_not_a_potential_root() -> None:
    result = check_potential_root(make_playbook(), "99")
    assert not result.ok
    assert not result.exists


def test_potential_root_allows_orphan_feeder_into_descendant() -> None:
    pb = make_playbook()
    pb["tasks"]["588"] = {
        "id": "588",
        "type": "regular",
        "task": {"name": "OrphanFeeder", "type": "regular"},
        "nextTasks": {"#none#": ["3"]},
        "view": {"position": {"x": -200, "y": 300}},
    }
    result = check_potential_root(pb, "1")
    assert result.ok
    assert result.orphan_feeder_ids == ["588"]
    assert "588" in result.descendant_ids
    assert result.outside_incoming_to_descendants
    assert result.outside_incoming_to_descendants[0].source_id == "588"


def test_potential_root_does_not_hang_on_converging_condition_branches() -> None:
    """Regression: orphan feeder walk must not loop when branches rejoin (e.g. task 21->23, 22->23)."""
    pb = make_playbook()
    pb["tasks"]["20"] = {
        "id": "20",
        "type": "title",
        "task": {"name": "Section", "type": "title"},
        "nextTasks": {"#none#": ["21"]},
    }
    pb["tasks"]["21"] = {
        "id": "21",
        "type": "condition",
        "task": {"name": "Branch?", "type": "condition"},
        "nextTasks": {"#default#": ["23"], "yes": ["22"]},
    }
    pb["tasks"]["22"] = {
        "id": "22",
        "type": "regular",
        "task": {"name": "Yes arm", "type": "regular"},
        "nextTasks": {"#none#": ["23"]},
    }
    pb["tasks"]["23"] = {
        "id": "23",
        "type": "title",
        "task": {"name": "After", "type": "title"},
        "nextTasks": {"#none#": ["3"]},
    }
    pb["tasks"]["2"]["nextTasks"] = {"yes": ["3"], "no": ["20"]}
    result = check_potential_root(pb, "22")
    assert result.exists
    assert isinstance(result.ok, bool)


def test_potential_root_still_fails_on_start_leak_into_descendant() -> None:
    pb = make_playbook()
    pb["tasks"]["0"]["nextTasks"] = {"#none#": ["1", "3"]}
    result = check_potential_root(pb, "1")
    assert not result.ok
    assert result.orphan_feeder_ids == []
