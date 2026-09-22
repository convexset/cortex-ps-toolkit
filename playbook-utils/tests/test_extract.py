from __future__ import annotations

from datetime import datetime, timezone

from playbook_utils.extract import (
    build_subplaybook,
    refactor_cluster_subplaybook_name,
    refactor_parent_copy_name,
    refactor_subplaybook_name,
    rewrite_parent,
)
from playbook_utils.graph import check_potential_root
from playbook_utils.keys import playbook_tasks, start_task_id, task_position, task_type
from playbook_utils.yaml_codec import dumps_yaml, prepare_for_upload
from tests.test_graph import make_playbook


def test_refactor_names() -> None:
    assert refactor_subplaybook_name("Main", "Alpha", task_id="7") == (
        "[REFACTOR-S] Main [LEAF from 7]"
    )
    assert refactor_cluster_subplaybook_name(
        "Main", "Start", "End", start_task_id="21", end_task_id="52"
    ) == "[REFACTOR-S] Main [INT from 21 to 52]"
    when = datetime(2026, 9, 9, 10, 51, 0, tzinfo=timezone.utc)
    assert refactor_parent_copy_name("Main", at=when) == (
        "[REFACTOR-M] Main [at 2026-09-09T10:51+00:00]"
    )
    naive = datetime(2026, 9, 9, 10, 51, 0)
    assert refactor_parent_copy_name("Main", at=naive).endswith("+00:00]")


def test_build_subplaybook_adds_start_and_keeps_descendants() -> None:
    source = make_playbook()
    sub = build_subplaybook(source, "1", name="Main / Alpha")
    assert sub["name"] == "Main / Alpha"
    assert start_task_id(sub) == "0"
    assert task_type(playbook_tasks(sub)["0"]) == "start"
    assert set(playbook_tasks(sub)) == {"0", "1", "2", "3", "4"}
    assert playbook_tasks(sub)["0"]["nextTasks"]["#none#"] == ["1"]
    assert sub["separateContext"] is True


def test_subplaybook_yaml_emits_separatecontext() -> None:
    source = make_playbook()
    sub = build_subplaybook(source, "1", name="Main / Alpha")
    prepared = prepare_for_upload(sub)
    assert prepared.get("separatecontext") is True
    yaml_text = dumps_yaml(sub)
    assert "separatecontext: true" in yaml_text


def test_rewrite_parent_inserts_leaf_and_removes_old_subgraph() -> None:
    source = make_playbook()
    rewritten = rewrite_parent(
        source,
        "1",
        subplaybook_name="Main / Alpha",
        copy_name="Main (factored)",
        padding=400,
    )
    tasks = playbook_tasks(rewritten)
    meta = rewritten["_refactor"]
    call_id = meta["subplaybook_task_id"]
    call = tasks[call_id]
    assert call["type"] == "playbook"
    assert call["task"]["playbookName"] == "Main / Alpha"
    assert call["separateContext"] is False
    assert "nextTasks" not in call
    assert tasks["0"]["nextTasks"]["#none#"] == [call_id]
    assert set(tasks) == {"0", call_id}
    assert "1" not in tasks
    assert meta["removed_task_ids"] == ["1", "2", "4", "3"]
    assert task_position(tasks[call_id]) == task_position(source["tasks"]["1"])
    assert rewritten["name"] == "Main (factored)"
    assert rewritten["sourcePlaybookID"] == source["id"]


def test_yaml_upload_uses_lowercase_keys_and_drops_ids() -> None:
    source = make_playbook()
    sub = build_subplaybook(source, "1", name="Main / Alpha")
    prepared = prepare_for_upload(sub)
    assert "starttaskid" in prepared
    assert "startTaskId" not in prepared
    first = prepared["tasks"]["1"]
    assert "nexttasks" in first
    assert "taskid" not in first
    assert "id" not in first.get("task", {})
    yaml_text = dumps_yaml(sub)
    assert "starttaskid:" in yaml_text
    assert "nexttasks:" in yaml_text
    assert "scriptName: s-alpha" in yaml_text
    assert "scriptid:" not in yaml_text


def test_build_subplaybook_includes_orphan_feeders() -> None:
    source = make_playbook()
    source["tasks"]["588"] = {
        "id": "588",
        "type": "regular",
        "task": {"name": "OrphanFeeder", "type": "regular"},
        "nextTasks": {"#none#": ["3"]},
        "view": {"position": {"x": -200, "y": 300}},
    }
    check = check_potential_root(source, "1")
    sub = build_subplaybook(source, "1", name="Main / Alpha", root_check=check)
    assert "588" in playbook_tasks(sub)
    assert set(playbook_tasks(sub)) == {"0", "1", "2", "3", "4", "588"}


def test_rewrite_parent_removes_orphan_feeders() -> None:
    source = make_playbook()
    source["tasks"]["588"] = {
        "id": "588",
        "type": "regular",
        "task": {"name": "OrphanFeeder", "type": "regular"},
        "nextTasks": {"#none#": ["3"]},
        "view": {"position": {"x": -200, "y": 300}},
    }
    check = check_potential_root(source, "1")
    rewritten = rewrite_parent(
        source,
        "1",
        subplaybook_name="Main / Alpha",
        copy_name="Main (factored)",
        root_check=check,
    )
    tasks = playbook_tasks(rewritten)
    assert "588" not in tasks
    assert set(tasks) == {"0", rewritten["_refactor"]["subplaybook_task_id"]}
    assert "588" in rewritten["_refactor"]["removed_task_ids"]


def test_rewrite_requires_potential_root() -> None:
    source = make_playbook()
    source["tasks"]["0"]["nextTasks"] = {"#none#": ["1", "3"]}
    assert not check_potential_root(source, "1").ok
    try:
        rewrite_parent(source, "1", subplaybook_name="X", copy_name="Y")
        assert False, "expected ValueError"
    except ValueError:
        pass
