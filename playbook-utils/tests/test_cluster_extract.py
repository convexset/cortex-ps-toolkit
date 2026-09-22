from __future__ import annotations

from typing import Dict

from playbook_utils.extract import (
    build_subplaybook_cluster,
    refactor_cluster_subplaybook_name,
    rewrite_parent_cluster,
    rewrite_parent_combined,
)
from playbook_utils.graph import check_cluster_extract, check_combined_extract
from playbook_utils.keys import playbook_tasks


def make_linear_playbook() -> Dict:
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
                "task": {"name": "StartCluster", "type": "regular"},
                "nextTasks": {"#none#": ["2"]},
                "view": {"position": {"x": 50, "y": 100}},
            },
            "2": {
                "id": "2",
                "type": "regular",
                "task": {"name": "Middle", "type": "regular"},
                "nextTasks": {"#none#": ["3"]},
                "view": {"position": {"x": 50, "y": 200}},
            },
            "3": {
                "id": "3",
                "type": "regular",
                "task": {"name": "EndCluster", "type": "regular"},
                "nextTasks": {"#none#": ["4"]},
                "view": {"position": {"x": 50, "y": 300}},
            },
            "4": {
                "id": "4",
                "type": "regular",
                "task": {"name": "After", "type": "regular"},
                "view": {"position": {"x": 50, "y": 400}},
            },
        },
    }


def test_check_cluster_extract_accepts_linear_segment() -> None:
    pb = make_linear_playbook()
    result = check_cluster_extract(pb, "1", "3")
    assert result.ok
    assert result.cluster_task_ids == ["1", "2", "3"]
    assert len(result.end_outgoing) == 1
    assert result.end_outgoing[0].target_id == "4"


def test_check_cluster_extract_rejects_conditional_end() -> None:
    pb = make_linear_playbook()
    pb["tasks"]["3"]["type"] = "condition"
    pb["tasks"]["3"]["task"]["type"] = "condition"
    pb["tasks"]["3"]["nextTasks"] = {"yes": ["4"], "no": ["4"]}
    pb["tasks"]["3"]["conditions"] = [{"label": "yes", "condition": []}]
    result = check_cluster_extract(pb, "1", "3")
    assert not result.ok
    assert any("conditional" in reason.lower() for reason in result.reasons)


def test_check_cluster_extract_rejects_outside_successor() -> None:
    pb = make_linear_playbook()
    pb["tasks"]["2"]["nextTasks"] = {"#none#": ["3", "4"]}
    result = check_cluster_extract(pb, "1", "3")
    assert not result.ok
    assert result.outside_outgoing


def test_rewrite_parent_cluster_replaces_segment() -> None:
    pb = make_linear_playbook()
    check = check_cluster_extract(pb, "1", "3")
    sub_name = refactor_cluster_subplaybook_name(
        "Main",
        "StartCluster",
        "EndCluster",
        start_task_id="1",
        end_task_id="3",
    )
    rewritten = rewrite_parent_cluster(
        pb,
        check,
        subplaybook_name=sub_name,
        subplaybook_id="sub-id",
        copy_name="Main (cluster)",
    )
    tasks = playbook_tasks(rewritten)
    call_id = rewritten["_refactor"]["subplaybook_task_id"]
    assert tasks["0"]["nextTasks"]["#none#"] == [call_id]
    assert tasks[call_id]["nextTasks"]["#none#"] == ["4"]
    assert tasks[call_id]["task"]["playbookId"] == "sub-id"
    assert set(tasks) == {"0", "4", call_id}


def test_rewrite_parent_combined_retargets_cluster_end_links() -> None:
    pb = make_linear_playbook()
    combined = check_combined_extract(pb, ["4"], [("1", "3")])
    assert combined.ok
    rewritten = rewrite_parent_combined(
        pb,
        cluster_checks=combined.clusters,
        cluster_subplaybook_names=["Cluster Sub"],
        task_ids=["4"],
        subplaybook_names=["Leaf Sub"],
        copy_name="Main combined",
        root_checks=combined.root_checks,
    )
    tasks = playbook_tasks(rewritten)
    cluster_call_id = rewritten["_refactor"]["cluster_extractions"][0]["subplaybook_task_id"]
    leaf_call_id = rewritten["_refactor"]["extractions"][0]["subplaybook_task_id"]
    assert tasks[cluster_call_id]["nextTasks"]["#none#"] == [leaf_call_id]
    assert "4" not in tasks
    assert leaf_call_id in tasks


def test_build_subplaybook_cluster_strips_end_outgoing() -> None:
    pb = make_linear_playbook()
    check = check_cluster_extract(pb, "1", "3")
    sub = build_subplaybook_cluster(pb, check, name="Cluster Sub")
    tasks = playbook_tasks(sub)
    assert set(tasks) == {"0", "1", "2", "3"}
    assert "nextTasks" not in tasks["3"]
