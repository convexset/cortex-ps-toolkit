"""Tests for refactor overwrite detection and confirmation gates."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cortex_ps_toolkit.playbooks.refactor_overwrite import (
    coalesce_overwrite_existing,
    list_refactor_name_conflicts,
    validate_overwrite_request,
)


def test_coalesce_overwrite_existing_defaults_true() -> None:
    assert coalesce_overwrite_existing(None) is True
    assert coalesce_overwrite_existing(True) is True
    assert coalesce_overwrite_existing(False) is False


@patch("cortex_ps_toolkit.playbooks.refactor_overwrite.find_playbook_in_index")
@patch("cortex_ps_toolkit.playbooks.refactor_overwrite.get_profile")
def test_list_refactor_name_conflicts_skips_source(mock_profile: MagicMock, mock_find: MagicMock) -> None:
    mock_profile.return_value = MagicMock(slug="lab")
    mock_find.side_effect = lambda _p, **kw: (
        {"id": "sub-1", "name": kw.get("name"), "modified": "2020"}
        if kw.get("name") == "[REFACTOR-S] Foo"
        else {"id": "src-1", "name": "[REFACTOR-M] Main", "modified": "2020"}
        if kw.get("name") == "[REFACTOR-M] Main"
        else None
    )
    rows = list_refactor_name_conflicts(
        "lab",
        subplaybook_names=["[REFACTOR-S] Foo"],
        parent_copy_name="[REFACTOR-M] Main",
        source_playbook_id="src-1",
    )
    assert len(rows) == 1
    assert rows[0]["name"] == "[REFACTOR-S] Foo"
    assert rows[0]["role"] == "sub_playbook"


def test_validate_overwrite_requires_confirmation() -> None:
    conflicts = [{"name": "[REFACTOR-S] X", "playbook_id": "p1"}]
    with pytest.raises(ValueError, match="overwrite_confirmed"):
        validate_overwrite_request(
            overwrite_existing=True,
            overwrite_confirmed=False,
            conflicts=conflicts,
        )
    validate_overwrite_request(
        overwrite_existing=True,
        overwrite_confirmed=True,
        conflicts=conflicts,
    )


def test_validate_overwrite_confirmed_without_flag() -> None:
    with pytest.raises(ValueError, match="overwrite_existing"):
        validate_overwrite_request(
            overwrite_existing=False,
            overwrite_confirmed=True,
            conflicts=[],
        )
