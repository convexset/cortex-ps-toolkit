"""Tests for BIOC cross-tenant copy."""

from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.credentials import CredentialProfile
from cortex_ps_toolkit.platform_admin.bioc_copy import copy_biocs_to_tenant
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


@patch("cortex_ps_toolkit.platform_admin.bioc_copy.refresh_section_cache")
@patch("cortex_ps_toolkit.platform_admin.bioc_copy.api.insert_biocs")
@patch("cortex_ps_toolkit.platform_admin.bioc_copy.api.get_bioc")
@patch("cortex_ps_toolkit.platform_admin.bioc_copy.plan_bioc_copy")
def test_copy_biocs_executes_insert(mock_plan, mock_get, mock_insert, _mock_refresh) -> None:
    source = _profile("src")
    target = _profile("tgt")
    mock_plan.return_value = {
        "source_profile": "src",
        "target_profile": "tgt",
        "section": "biocs",
        "entries": [{"source_name": "B1", "target_name": "B1", "action": "copy"}],
        "has_conflicts": False,
    }
    mock_get.return_value = {"name": "B1", "rule_id": 9, "type": "EXECUTION"}
    mock_insert.return_value = ({}, 200)

    result = copy_biocs_to_tenant(source, target, ["B1"])
    assert result["executed"] is True
    assert result["results"][0]["status"] == 200
    mock_insert.assert_called_once()
