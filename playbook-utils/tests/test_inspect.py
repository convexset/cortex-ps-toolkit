from __future__ import annotations

from playbook_utils.graph import total_successors
from playbook_utils.inspect import (
    evaluate_expect,
    inspect_playbook,
    inspect_task,
    parse_expect_spec,
    resolve_task_ref,
)
from tests.test_graph import make_playbook


def test_total_successors_excludes_self() -> None:
    pb = make_playbook()
    assert total_successors(pb, "1") == ["2", "4", "3"]
    assert total_successors(pb, "3") == []


def test_inspect_task_alpha_is_potential_root() -> None:
    report = inspect_task(make_playbook(), "1")
    assert report.name == "Alpha"
    assert report.successor_count == 3
    assert report.potential_root is True


def test_inspect_task_nopath_is_not_potential_root() -> None:
    report = inspect_task(make_playbook(), "4")
    assert report.name == "NoPath"
    assert report.successor_count == 1
    assert report.potential_root is False
    assert report.potential_root_reasons


def test_inspect_playbook_lists_all_tasks() -> None:
    reports = inspect_playbook(make_playbook())
    assert [r.task_id for r in reports] == ["0", "1", "2", "3", "4"]


def test_resolve_task_ref_accepts_id_or_unique_name() -> None:
    pb = make_playbook()
    assert resolve_task_ref(pb, "1") == "1"
    assert resolve_task_ref(pb, "Alpha") == "1"


def test_parse_and_evaluate_expect_specs() -> None:
    spec = parse_expect_spec("1,name=Alpha,successors=3,root=yes")
    assert spec.task_id == "1"
    assert spec.name == "Alpha"
    assert spec.successors == 3
    assert spec.potential_root is True
    pb = make_playbook()
    assert evaluate_expect(pb, spec).ok
    bad = parse_expect_spec("4,name=NoPath,successors=1,root=yes")
    result = evaluate_expect(pb, bad)
    assert not result.ok
    assert any("potential_root" in item for item in result.mismatches)
