"""Tests for design content delete support matrix."""

from __future__ import annotations

import pytest

from cortex_ps_toolkit.credentials import CredentialProfile
from cortex_ps_toolkit.design_content.delete import _delete_supported, plan_asset_delete
from cortex_ps_toolkit.platforms import Platform


def _profile(platform: Platform) -> CredentialProfile:
    return CredentialProfile(
        id="id-1",
        label="Lab",
        slug="lab",
        url="https://tenant.example.test",
        api_id="1",
        key="secret",
        tenant_type=platform,
        verify_ssl=True,
    )


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        (Platform.XSOAR6, True),
        (Platform.XSOAR8, True),
        (Platform.XSIAM, True),
        (Platform.XDR5, True),
        (Platform.AGENTIX, True),
    ],
)
def test_layout_delete_supported_on_cloud_and_xsoar(platform: Platform, expected: bool) -> None:
    assert _delete_supported(_profile(platform), "layouts") is expected


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        (Platform.XSOAR6, True),
        (Platform.XSOAR8, True),
        (Platform.XSIAM, False),
    ],
)
def test_classifier_delete_matrix(platform: Platform, expected: bool) -> None:
    assert _delete_supported(_profile(platform), "classifiers") is expected


def test_plan_asset_delete_marks_unsupported_classifier_on_xsiam() -> None:
    plan = plan_asset_delete(_profile(Platform.XSIAM), "classifiers", ["mapper-1"])
    assert plan["entries"][0]["deletable"] is False
