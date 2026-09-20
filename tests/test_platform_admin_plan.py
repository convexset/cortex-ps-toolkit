"""Tests for platform admin copy/delete preview planning."""

from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.credentials import CredentialProfile
from cortex_ps_toolkit.platform_admin.plan import (
    plan_bioc_copy,
    plan_bioc_delete,
    plan_correlation_copy,
    plan_correlation_delete,
    plan_indicator_delete,
)
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


@patch("cortex_ps_toolkit.platform_admin.plan.refresh_section_cache")
@patch("cortex_ps_toolkit.platform_admin.plan.api.get_correlation_rule")
def test_plan_correlation_copy_skip_when_exists(mock_get, _mock_refresh) -> None:
    source = _profile("src")
    target = _profile("tgt")
    mock_get.side_effect = lambda profile, name: {"name": name} if profile.slug == "src" else {"name": name}

    plan = plan_correlation_copy(source, target, ["Rule A"], overwrite=False)
    assert plan["entries"][0]["action"] == "skip"
    assert plan["has_conflicts"] is False


@patch("cortex_ps_toolkit.platform_admin.plan.refresh_section_cache")
@patch("cortex_ps_toolkit.platform_admin.plan.api.get_correlation_rule")
def test_plan_correlation_copy_conflict(mock_get, _mock_refresh) -> None:
    source = _profile("src")
    target = _profile("tgt")
    mock_get.side_effect = lambda _profile, name: {"name": name}

    plan = plan_correlation_copy(source, target, ["Rule A"], stop_on_conflict=True)
    assert plan["entries"][0]["action"] == "conflict"
    assert plan["has_conflicts"] is True


def test_plan_correlation_delete_lists_names() -> None:
    profile = _profile("lab")
    plan = plan_correlation_delete(profile, ["A", "B"])
    assert plan["profile"] == "lab"
    assert len(plan["entries"]) == 2
    assert all(entry["deletable"] for entry in plan["entries"])


@patch("cortex_ps_toolkit.platform_admin.plan.refresh_section_cache")
@patch("cortex_ps_toolkit.platform_admin.plan.api.get_bioc")
def test_plan_bioc_copy_missing_source(mock_get, _mock_refresh) -> None:
    source = _profile("src")
    target = _profile("tgt")
    mock_get.return_value = None

    plan = plan_bioc_copy(source, target, ["Missing"])
    assert plan["entries"][0]["action"] == "missing"


def test_plan_bioc_delete() -> None:
    profile = _profile("lab")
    plan = plan_bioc_delete(profile, ["BIOC-1"])
    assert plan["section"] == "biocs"
    assert plan["entries"][0]["name"] == "BIOC-1"


def test_plan_indicator_delete() -> None:
    profile = _profile("lab")
    plan = plan_indicator_delete(profile, ["114", "115"])
    assert plan["section"] == "indicators"
    assert len(plan["entries"]) == 2
