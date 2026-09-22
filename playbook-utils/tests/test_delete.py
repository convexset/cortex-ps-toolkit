from __future__ import annotations

from playbook_utils.cli import build_parser
from playbook_utils.delete import (
    delete_playbook_rows,
    name_starts_with,
    order_playbooks_for_delete,
)


def test_name_prefix_is_case_sensitive() -> None:
    assert name_starts_with("[REFACTOR] Main", "[REFACTOR")
    assert name_starts_with("[REFACTOR-SUBPLAYBOOK] Main [from X]", "[REFACTOR")
    assert not name_starts_with("[refactor] Main", "[REFACTOR")
    assert not name_starts_with("Default", "[REFACTOR")


def test_order_deletes_parents_before_subplaybooks() -> None:
    rows = [
        {"id": "s1", "name": "[REFACTOR-SUBPLAYBOOK] Main [from A]"},
        {"id": "p1", "name": "[REFACTOR] Main [at 2026-09-09T13:10:42Z]"},
        {"id": "s2", "name": "[REFACTOR-SUBPLAYBOOK] Other [from B]"},
        {"id": "p2", "name": "[REFACTOR] Other [at 2026-09-09T13:11:11Z]"},
    ]
    ordered = order_playbooks_for_delete(rows)
    assert [row["id"] for row in ordered] == ["p1", "p2", "s1", "s2"]


def test_order_deletes_refactor_m_before_refactor_s() -> None:
    rows = [
        {"id": "s1", "name": "[REFACTOR-S] Main [LEAF from 366]"},
        {"id": "s2", "name": "[REFACTOR-S] Main [INT from 21 to 52]"},
        {"id": "s3", "name": "[REFACTOR-S-LEAF] Main [from 366]"},
        {"id": "p1", "name": "[REFACTOR-M] Main [at 2026-09-09T19:14+00:00]"},
    ]
    ordered = order_playbooks_for_delete(rows)
    assert ordered[0]["id"] == "p1"
    assert {row["id"] for row in ordered[1:]} == {"s1", "s2", "s3"}


def test_delete_playbook_rows_records_failures() -> None:
    def delete_fn(*, playbook_id=None, name=None):
        if playbook_id == "bad":
            raise RuntimeError("nope")
        return {"id": playbook_id}

    outcomes = delete_playbook_rows(
        [{"id": "good", "name": "A"}, {"id": "bad", "name": "B"}],
        delete_fn=delete_fn,
    )
    assert outcomes[0]["ok"] is True
    assert outcomes[1]["ok"] is False
    assert "nope" in outcomes[1]["error"]


def test_extract_cli_has_damp_run_not_dry_run() -> None:
    parser = build_parser()
    args = parser.parse_args(["extract", "--playbook", "P", "--task", "1", "--damp-run"])
    assert args.damp_run is True
    try:
        parser.parse_args(["extract", "--playbook", "P", "--task", "1", "--dry-run"])
        raise AssertionError("expected --dry-run to be rejected")
    except SystemExit:
        pass
