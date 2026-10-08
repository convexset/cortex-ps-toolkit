"""Delete preview operation plan envelope."""

from __future__ import annotations

from cortex_ps_toolkit.content.operation_plan import wrap_delete_plan, wrap_refactor_plan


def test_wrap_delete_plan_lists_shape() -> None:
    legacy = {
        "profile": "lab",
        "items": [
            {"list_id": "a", "name": "ListA", "action": "delete"},
            {"list_id": "b", "name": "Sys", "action": "blocked_system"},
        ],
        "counts": {"total": 2, "delete": 1, "blocked_system": 1, "not_found": 0},
        "would_delete": True,
    }
    plan = wrap_delete_plan(legacy, operation="lists.delete")
    assert plan["plan_version"] == 1
    assert plan["summary"]["delete"] == 1
    assert plan["summary"]["blocked"] == 1
    assert plan["items"][1]["action"] == "blocked"
    assert any(r["code"] == "PERMANENT_DELETE" for r in plan["risks"])


def test_wrap_refactor_plan_includes_extractions() -> None:
    legacy = {
        "profile": "lab",
        "ok": True,
        "source_playbook": {"id": "pb1", "name": "Root_PB"},
        "parent_copy_name": "Root_PB [REFACTOR-M]",
        "extractions": [{"kind": "leaf", "task_id": "2", "subplaybook_name": "Root_PB_Sub_2"}],
        "existing_targets": [],
        "reasons": [],
    }
    plan = wrap_refactor_plan(legacy)
    assert plan["plan_version"] == 1
    assert plan["operation"] == "playbooks.refactor"
    assert len(plan["items"]) == 2
