"""Design content copy-as-new planning."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.design_content.copy import plan_asset_copy


def _profile(slug: str) -> MagicMock:
    profile = MagicMock()
    profile.slug = slug
    profile.tenant_type = "xsoar8"
    return profile


@patch("cortex_ps_toolkit.design_content.copy.get_item_body")
@patch("cortex_ps_toolkit.design_content.copy._cached_target_ids")
@patch("cortex_ps_toolkit.design_content.copy.get_profile")
def test_plan_asset_copy_as_new_on_collision(mock_get_profile, mock_target_ids, mock_body) -> None:
    source = _profile("src")
    target = _profile("dst")
    mock_get_profile.side_effect = lambda slug: source if slug == "src" else target
    mock_target_ids.return_value = {"ExistingLayout"}
    mock_body.return_value = {"name": "ExistingLayout", "id": "ExistingLayout"}

    plan = plan_asset_copy(
        source,
        target,
        "layouts",
        ["ExistingLayout"],
        copy_mode="copy_as_new",
        rename_suffix="_lab",
    )

    assert plan["plan_version"] == 1
    entry = plan["entries"][0]
    assert entry["action"] == "copy_as_new"
    assert entry["target_name"] == "ExistingLayout_lab"
