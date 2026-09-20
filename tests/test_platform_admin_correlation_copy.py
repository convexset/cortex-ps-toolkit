"""Tests for correlation rule cross-tenant copy execution."""

from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.credentials import CredentialProfile
from cortex_ps_toolkit.platform_admin.copy import copy_correlation_rules_to_tenant
from cortex_ps_toolkit.platforms import Platform


def _profile(slug: str) -> CredentialProfile:
    return CredentialProfile(
        id=f"id-{slug}",
        label=slug,
        slug=slug,
        url="https://tenant.example.test",
        api_id="1",
        key="secret",
        tenant_type=Platform.XSIAM,
        verify_ssl=True,
    )


@patch("cortex_ps_toolkit.platform_admin.copy.refresh_section_cache")
@patch("cortex_ps_toolkit.platform_admin.copy.api.insert_correlation_rules")
@patch("cortex_ps_toolkit.platform_admin.copy.api.get_correlation_rule")
@patch("cortex_ps_toolkit.platform_admin.copy.plan_correlation_copy")
def test_copy_correlation_rules_executes_insert(mock_plan, mock_get, mock_insert, _mock_refresh) -> None:
    source = _profile("src")
    target = _profile("tgt")
    mock_plan.return_value = {
        "source_profile": "src",
        "target_profile": "tgt",
        "section": "correlation-rules",
        "entries": [{"source_name": "Rule-A", "target_name": "Rule-A", "action": "copy"}],
        "has_conflicts": False,
    }
    mock_get.return_value = {"name": "Rule-A", "rule_id": 1}
    mock_insert.return_value = ({}, 200)

    result = copy_correlation_rules_to_tenant(source, target, ["Rule-A"])
    assert result["executed"] is True
    assert result["results"][0]["status"] == 200
    mock_insert.assert_called_once()
