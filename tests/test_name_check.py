"""Unit tests for copy name-check API helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.content.name_check import check_proposed_names, proposals_from_copy_selection


@patch("cortex_ps_toolkit.content.name_check.find_script_in_index")
@patch("cortex_ps_toolkit.content.name_check.get_profile")
def test_check_proposed_names_collision(mock_profile, mock_find) -> None:
    mock_profile.return_value.slug = "target-lab"
    mock_find.side_effect = lambda _p, name: {"id": "t1", "name": name} if name == "Taken" else None
    result = check_proposed_names(
        "target-lab",
        "scripts",
        [
            {"key": "s1", "source_name": "Foo", "proposed_name": "Foo_copy"},
            {"key": "s2", "source_name": "Bar", "proposed_name": "Taken"},
        ],
    )
    assert result["collision_count"] == 1
    assert result["checks"][0]["exists"] is False
    assert result["checks"][1]["exists"] is True
    assert result["all_available"] is False


def test_proposals_from_copy_selection_with_map() -> None:
    rows = proposals_from_copy_selection(
        kind="lists",
        items=[{"id": "abc", "name": "MyList"}],
        rename_suffix="_lab",
        rename_map={"abc": "CustomName"},
    )
    assert rows[0]["proposed_name"] == "CustomName"
