"""Tests for indicator cross-tenant copy."""

from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.credentials import CredentialProfile
from cortex_ps_toolkit.platform_admin.api import prepare_cortex_indicator_write
from cortex_ps_toolkit.platform_admin.indicator_copy import copy_indicators_to_tenant
from cortex_ps_toolkit.platform_admin.plan import plan_indicator_copy
from cortex_ps_toolkit.platforms import Platform


def _profile(slug: str, platform: Platform = Platform.XSIAM) -> CredentialProfile:
    return CredentialProfile(
        id=f"id-{slug}",
        label=slug,
        slug=slug,
        url="https://tenant.example.test",
        api_id="1",
        key="secret",
        tenant_type=platform,
        verify_ssl=True,
    )


def test_prepare_cortex_indicator_write_strips_rule_id() -> None:
    doc = prepare_cortex_indicator_write({
        "rule_id": "99",
        "indicator": "evil.example.test",
        "type": "DOMAIN_NAME",
        "reputation": "BAD",
    })
    assert "rule_id" not in doc
    assert doc["indicator"] == "evil.example.test"
    assert doc["reliability"] == "C"


@patch("cortex_ps_toolkit.platform_admin.plan.refresh_section_cache")
@patch("cortex_ps_toolkit.platform_admin.plan.api.find_indicator_by_value")
@patch("cortex_ps_toolkit.platform_admin.plan.api.get_indicator")
def test_plan_indicator_copy_incompatible_platforms(mock_get, mock_find, _mock_refresh) -> None:
    source = _profile("xsiam", Platform.XSIAM)
    target = _profile("x6", Platform.XSOAR6)
    mock_get.return_value = {"indicator": "a.example.test", "rule_id": "1"}
    plan = plan_indicator_copy(source, target, ["1"])
    assert plan["compatible"] is False
    assert plan["entries"][0]["action"] == "incompatible"


@patch("cortex_ps_toolkit.platform_admin.indicator_copy.refresh_section_cache")
@patch("cortex_ps_toolkit.platform_admin.indicator_copy.api.insert_indicators")
@patch("cortex_ps_toolkit.platform_admin.indicator_copy.api.get_indicator")
@patch("cortex_ps_toolkit.platform_admin.indicator_copy.plan_indicator_copy")
def test_copy_indicators_cortex_insert(mock_plan, mock_get, mock_insert, _mock_refresh) -> None:
    source = _profile("src", Platform.XSIAM)
    target = _profile("tgt", Platform.XDR5)
    mock_plan.return_value = {
        "source_profile": "src",
        "target_profile": "tgt",
        "section": "indicators",
        "entries": [{"source_id": "57", "action": "copy", "lookup": "evil.example.test"}],
        "has_conflicts": False,
        "compatible": True,
    }
    mock_get.return_value = {"rule_id": "57", "indicator": "evil.example.test", "type": "DOMAIN_NAME"}
    mock_insert.return_value = ({}, 200)

    result = copy_indicators_to_tenant(source, target, ["57"])
    assert result["executed"] is True
    mock_insert.assert_called_once()


@patch("cortex_ps_toolkit.platform_admin.indicator_copy.refresh_section_cache")
@patch("cortex_ps_toolkit.platform_admin.indicator_copy.api.create_xsoar_indicator")
@patch("cortex_ps_toolkit.platform_admin.indicator_copy.api.get_indicator")
@patch("cortex_ps_toolkit.platform_admin.indicator_copy.plan_indicator_copy")
def test_copy_indicators_xsoar_uses_create(mock_plan, mock_get, mock_create, _mock_refresh) -> None:
    source = _profile("src", Platform.XSOAR6)
    target = _profile("tgt", Platform.XSOAR8)
    mock_plan.return_value = {
        "source_profile": "src",
        "target_profile": "tgt",
        "section": "indicators",
        "entries": [{"source_id": "114", "action": "copy", "lookup": "8.8.8.8"}],
        "has_conflicts": False,
        "compatible": True,
    }
    mock_get.return_value = {"id": "114", "value": "8.8.8.8", "indicator_type": "IP"}
    mock_create.return_value = ({}, 200)

    result = copy_indicators_to_tenant(source, target, ["114"])
    assert result["executed"] is True
    mock_create.assert_called_once()
