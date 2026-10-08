"""Batch / basket name-check helpers."""

from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.content.name_check import (
    asset_to_name_check,
    check_basket_proposed_names,
    check_proposed_names_batch,
)


def test_asset_to_name_check_mapping() -> None:
    assert asset_to_name_check("scripts") == ("scripts", None)
    assert asset_to_name_check("layouts") == ("design", "layouts")
    assert asset_to_name_check("integrations") == (None, None)


@patch("cortex_ps_toolkit.content.name_check.find_script_in_index")
@patch("cortex_ps_toolkit.content.name_check.find_list_in_index")
@patch("cortex_ps_toolkit.content.name_check.get_profile")
def test_check_basket_groups_by_kind(mock_profile, mock_list, mock_script) -> None:
    mock_profile.return_value.slug = "tgt"
    mock_list.return_value = None
    mock_script.return_value = None
    result = check_basket_proposed_names(
        "tgt",
        [
            {"asset": "scripts", "id": "s1", "name": "ScriptA"},
            {"asset": "lists", "id": "l1", "name": "ListA"},
            {"asset": "integrations", "id": "i1", "name": "IntA"},
        ],
        rename_suffix="_x",
    )
    assert result["group_count"] == 2
    assert "integrations" in (result.get("skipped_assets") or [])


@patch("cortex_ps_toolkit.content.name_check.check_proposed_names")
@patch("cortex_ps_toolkit.content.name_check.get_profile")
def test_check_proposed_names_batch(mock_profile, mock_check) -> None:
    mock_profile.return_value.slug = "tgt"
    mock_check.return_value = {"checks": [{"proposed_name": "A", "exists": False}], "collision_count": 0}
    out = check_proposed_names_batch(
        "tgt",
        [
            {"kind": "scripts", "items": [{"id": "1", "name": "A"}], "rename_suffix": "_copy"},
        ],
    )
    assert out["group_count"] == 1
    assert out["checks"][0]["kind"] == "scripts"
