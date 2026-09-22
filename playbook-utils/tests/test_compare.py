from __future__ import annotations

import copy

from playbook_utils.compare import (
    canonicalize,
    compare_potential_roots,
    compare_source_to_downloaded_subplaybook,
)
from playbook_utils.extract import build_subplaybook
from tests.test_graph import make_playbook


def _renumber(playbook: dict, mapping: dict[str, str]) -> dict:
    pb = copy.deepcopy(playbook)
    new_tasks = {}
    for old_id, node in pb["tasks"].items():
        new_id = mapping.get(old_id, old_id)
        node = copy.deepcopy(node)
        node["id"] = new_id
        nt = node.get("nextTasks") or {}
        rewritten = {}
        for label, targets in nt.items():
            rewritten[label] = [mapping.get(t, t) for t in targets]
        if rewritten:
            node["nextTasks"] = rewritten
        new_tasks[new_id] = node
    pb["tasks"] = new_tasks
    if pb.get("startTaskId") in mapping:
        pb["startTaskId"] = mapping[pb["startTaskId"]]
    return pb


def test_canonical_order_is_stable_with_renumbered_ids() -> None:
    left = make_playbook()
    right = _renumber(left, {"0": "10", "1": "11", "2": "12", "3": "13", "4": "14"})
    compared = compare_potential_roots(left, "1", right, "11")
    assert compared.equal
    assert [n.name for n in compared.left.nodes] == ["Alpha", "Branch", "NoPath", "YesPath"]


def test_canonical_handles_descendant_cycles() -> None:
    pb = make_playbook()
    pb["tasks"]["4"]["nextTasks"] = {"#none#": ["2"]}
    graph = canonicalize(pb, "1")
    names = [n.name for n in graph.nodes]
    assert names[0] == "Alpha"
    assert "Branch" in names
    indexes = {n.name: n.index for n in graph.nodes}
    branch = next(n for n in graph.nodes if n.name == "Branch")
    assert set(sum(branch.next_tasks.values(), [])) == {indexes["YesPath"], indexes["NoPath"]}


def test_compare_detects_payload_mismatch() -> None:
    left = make_playbook()
    right = copy.deepcopy(left)
    right["tasks"]["3"]["task"]["name"] = "Changed"
    compared = compare_potential_roots(left, "1", right, "1")
    assert not compared.equal
    assert any("YesPath" in str(d.left) or "Changed" in str(d.right) for d in compared.diffs)


def test_compare_skips_start_on_built_subplaybook() -> None:
    source = make_playbook()
    sub = build_subplaybook(source, "1", name="Main / Alpha")
    compared = compare_source_to_downloaded_subplaybook(source, "1", sub)
    assert compared.equal
    assert compared.right.skipped_start_id is not None
    assert compared.left.skipped_start_id is None


def test_compare_equates_xsiam_yaml_key_aliases() -> None:
    """XSIAM get returns lowercase YAML; source cache is camelCase API JSON."""
    left = make_playbook()
    left["tasks"]["1"]["task"]["isCommand"] = True
    left["tasks"]["1"]["task"]["scriptId"] = "Builtin|||setIncident"
    left["tasks"]["1"]["scriptArguments"] = {
        "foo": {"complex": {"root": "inputs.x", "filters": None}}
    }
    right = copy.deepcopy(left)
    node = right["tasks"]["1"]
    node["separatecontext"] = node.pop("separateContext", False)
    node["scriptarguments"] = {
        "foo": {"complex": {"root": "inputs.x"}}
    }
    node.pop("scriptArguments", None)
    inner = node["task"]
    inner["iscommand"] = inner.pop("isCommand")
    inner["script"] = inner.pop("scriptId")
    compared = compare_potential_roots(left, "1", right, "1")
    assert compared.equal, compared.human_summary()


def test_compare_equates_playbook_id_and_yaml_playbook_name() -> None:
    left = make_playbook()
    left["tasks"]["4"]["type"] = "playbook"
    left["tasks"]["4"]["task"]["type"] = "playbook"
    left["tasks"]["4"]["task"]["playbookId"] = "PAN-OS - Block IP and URL - External Dynamic List"
    right = copy.deepcopy(left)
    inner = right["tasks"]["4"]["task"]
    inner["playbookName"] = inner.pop("playbookId")
    compared = compare_potential_roots(left, "1", right, "1")
    assert compared.equal, compared.human_summary()


def test_compare_equates_command_script_id_with_and_without_brand() -> None:
    left = make_playbook()
    left["tasks"]["1"]["task"]["isCommand"] = True
    left["tasks"]["1"]["task"]["scriptId"] = "|||checkpoint-block-ip"
    right = copy.deepcopy(left)
    right["tasks"]["1"]["task"]["scriptId"] = "Check Point|||checkpoint-block-ip"
    right["tasks"]["1"]["task"]["brand"] = "Check Point"
    compared = compare_potential_roots(left, "1", right, "1")
    assert compared.equal, compared.human_summary()


def test_compare_drops_nested_empty_transformer_args() -> None:
    left = make_playbook()
    left["tasks"]["1"]["scriptArguments"] = {
        "emailauthenticitycheck": {"complex": {"transformers": [{"args": {"limit": {}}}]}}
    }
    right = copy.deepcopy(left)
    right["tasks"]["1"]["scriptArguments"]["emailauthenticitycheck"]["complex"]["transformers"][0]["args"] = {}
    compared = compare_potential_roots(left, "1", right, "1")
    assert compared.equal, compared.human_summary()


def test_compare_ignores_ids_and_views() -> None:
    left = make_playbook()
    right = copy.deepcopy(left)
    right["tasks"]["1"]["id"] = "999"
    right["tasks"]["1"]["taskId"] = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    right["tasks"]["1"]["view"] = {"position": {"x": 9999, "y": 9999}}
    compared = compare_potential_roots(left, "1", right, "1")
    assert compared.equal


def test_unfiltered_compare_flags_id_and_view() -> None:
    from playbook_utils.compare import summarize_diff_paths, unfiltered_field_policy

    left = make_playbook()
    right = copy.deepcopy(left)
    right["tasks"]["1"]["id"] = "999"
    right["tasks"]["1"]["view"] = {"position": {"x": 9999, "y": 9999}}
    compared = compare_potential_roots(
        left, "1", right, "1", policy=unfiltered_field_policy()
    )
    assert not compared.equal
    paths = {d.path for d in compared.diffs}
    assert any(p.endswith(".id") for p in paths)
    assert any("view" in p for p in paths)
    counts = summarize_diff_paths(compared.diffs)
    assert counts["by_leaf_key"]["id"] >= 1
    summary = compared.human_summary()
    assert "all diffs:" in summary
    assert "..." not in summary.split("all diffs:", 1)[1]
