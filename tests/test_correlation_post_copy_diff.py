"""Post-copy diff on correlation rule copy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.platform_admin.copy import copy_correlation_rules_to_tenant


def _profile(slug: str) -> MagicMock:
    profile = MagicMock()
    profile.slug = slug
    profile.tenant_type = "xsiam"
    return profile


@patch("cortex_ps_toolkit.platform_admin.copy.refresh_section_cache")
@patch("cortex_ps_toolkit.platform_admin.copy.api.insert_correlation_rules")
@patch("cortex_ps_toolkit.platform_admin.copy.api.get_correlation_rule")
@patch("cortex_ps_toolkit.platform_admin.copy.plan_correlation_copy")
@patch("cortex_ps_toolkit.platform_admin.copy.get_profile")
def test_correlation_copy_post_copy_diff(
    mock_get_profile,
    mock_plan,
    mock_get_rule,
    mock_insert,
    _mock_refresh,
) -> None:
    source = _profile("src")
    target = _profile("dst")
    mock_get_profile.side_effect = lambda slug: source if slug == "src" else target
    rule_doc = {"name": "Rule A", "alert_name": "Rule A", "logic": {}}
    mock_plan.return_value = {
        "entries": [{"source_name": "Rule A", "target_name": "Rule A", "action": "copy"}],
        "has_conflicts": False,
    }
    mock_get_rule.return_value = rule_doc
    mock_insert.return_value = ({}, 200)

    result = copy_correlation_rules_to_tenant(
        "src",
        "dst",
        ["Rule A"],
        post_copy_diff=True,
    )

    assert result["post_copy_diff"] is True
    assert result["results"][0].get("post_copy_diff")
    assert result.get("copy_diff_report")
