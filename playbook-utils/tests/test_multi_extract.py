from __future__ import annotations

from typing import Dict

from playbook_utils.extract import rewrite_parent_multi
from playbook_utils.graph import check_multi_extract
from playbook_utils.keys import playbook_tasks
from tests.test_graph import make_playbook


def make_parallel_playbook() -> Dict:
    pb = make_playbook()
    pb["tasks"]["0"]["nextTasks"] = {"#none#": ["1", "5"]}
    pb["tasks"]["5"] = {
        "id": "5",
        "type": "regular",
        "task": {"name": "Parallel", "type": "regular"},
        "view": {"position": {"x": 300, "y": 100}},
    }
    return pb


def test_check_multi_extract_allows_non_overlapping_successors() -> None:
    pb = make_parallel_playbook()
    result = check_multi_extract(pb, ["1", "5"])
    assert result.ok
    assert not result.sequence_conflicts


def test_check_multi_extract_rejects_any_mutual_successor() -> None:
    pb = make_playbook()
    forward = check_multi_extract(pb, ["1", "3"])
    assert not forward.ok
    assert any(c["later_task_id"] == "3" for c in forward.sequence_conflicts)

    backward = check_multi_extract(pb, ["3", "1"])
    assert not backward.ok
    assert any({c["earlier_task_id"], c["later_task_id"]} == {"1", "3"} for c in backward.sequence_conflicts)


def test_rewrite_parent_multi_inserts_two_calls() -> None:
    pb = make_parallel_playbook()
    check = check_multi_extract(pb, ["1", "5"])
    rewritten = rewrite_parent_multi(
        pb,
        ["1", "5"],
        subplaybook_names=["Sub Alpha", "Sub Parallel"],
        copy_name="Main (multi)",
        root_checks=check.root_checks,
    )
    tasks = playbook_tasks(rewritten)
    meta = rewritten["_refactor"]
    assert len(meta["extractions"]) == 2
    call_ids = [item["subplaybook_task_id"] for item in meta["extractions"]]
    assert tasks[call_ids[0]]["task"]["playbookName"] == "Sub Alpha"
    assert tasks[call_ids[1]]["task"]["playbookName"] == "Sub Parallel"


def test_rewrite_parent_multi_binds_subplaybooks_by_id() -> None:
    pb = make_parallel_playbook()
    check = check_multi_extract(pb, ["1", "5"])
    rewritten = rewrite_parent_multi(
        pb,
        ["1", "5"],
        subplaybook_names=["Sub Alpha", "Sub Parallel"],
        subplaybook_ids=["id-alpha", "id-parallel"],
        copy_name="Main (multi)",
        root_checks=check.root_checks,
    )
    tasks = playbook_tasks(rewritten)
    call_ids = [item["subplaybook_task_id"] for item in rewritten["_refactor"]["extractions"]]
    assert tasks[call_ids[0]]["task"]["playbookId"] == "id-alpha"
    assert "playbookName" not in tasks[call_ids[0]]["task"]
    assert tasks[call_ids[1]]["task"]["playbookId"] == "id-parallel"
    assert "1" not in tasks
    assert "5" not in tasks
    assert rewritten["name"] == "Main (multi)"
