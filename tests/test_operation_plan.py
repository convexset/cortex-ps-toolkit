"""Unit tests for operation plan envelope."""

from __future__ import annotations

from cortex_ps_toolkit.content.copy_modes import classify_copy_action, parse_copy_mode
from cortex_ps_toolkit.content.operation_plan import (
    build_plan_summary,
    entry_row_to_plan_item,
    wrap_copy_plan,
    wrap_legacy_preview_plan,
)


def test_parse_copy_mode_legacy_overwrite() -> None:
    assert parse_copy_mode(overwrite=True) == "overwrite"
    assert parse_copy_mode() == "skip"
    assert parse_copy_mode(copy_mode="copy_as_new") == "copy_as_new"


def test_classify_copy_as_new() -> None:
    existing = {"id": "t1", "name": "Foo"}
    action, extra = classify_copy_action(
        existing=existing,
        mode="copy_as_new",
        source_name="Foo",
        rename_suffix="_lab",
        name_exists=lambda n: n == "Foo_lab",
    )
    assert action == "conflict"
    assert extra.get("proposed_name") == "Foo_lab"


def test_wrap_copy_plan_includes_risks() -> None:
    legacy = {
        "source_profile": "a",
        "target_profile": "b",
        "overwrite": True,
        "stop_on_conflict": False,
        "items": [
            {"name": "X", "action": "update"},
            {"name": "Y", "action": "copy"},
        ],
        "counts": {"total": 2, "copy": 1, "update": 1, "skip": 0, "conflict": 0},
        "would_abort": False,
        "conflicts": [],
    }
    plan = wrap_copy_plan(legacy, operation="lists.copy", mode="overwrite")
    assert plan["plan_version"] == 1
    assert plan["summary"]["update"] == 1
    assert any(r["code"] == "OVERWRITE" for r in plan["risks"])
    assert plan["mode_description"]


def test_entry_row_to_plan_item_uses_target_name() -> None:
    item = entry_row_to_plan_item(
        {"source_name": "A", "target_name": "A-copy", "action": "copy"},
    )
    assert item["name"] == "A-copy"
    assert item["action"] == "copy"


def test_wrap_legacy_preview_plan_from_entries() -> None:
    legacy = {
        "source_profile": "a",
        "target_profile": "b",
        "entries": [
            {"source_name": "Rule1", "target_name": "Rule1", "action": "copy"},
            {"source_name": "Rule2", "target_name": "Rule2", "action": "skip"},
        ],
        "has_conflicts": False,
    }
    plan = wrap_legacy_preview_plan(
        legacy,
        operation="platform_admin.correlation_copy",
        overwrite=False,
        stop_on_conflict=False,
    )
    assert plan["plan_version"] == 1
    assert plan["summary"]["create"] == 1
    assert plan["summary"]["skip"] == 1
    assert len(plan["items"]) == 2
