"""Tests for profile content capability flags."""

from __future__ import annotations

from cortex_ps_toolkit.content_capabilities import profile_capabilities
from cortex_ps_toolkit.credentials import CredentialProfile
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


def test_xsoar6_layout_delete_supported_classifier_delete_supported() -> None:
    caps = profile_capabilities(_profile(Platform.XSOAR6))
    assert caps["object_setup"]["layouts"]["delete"] is True
    assert caps["object_setup"]["classifiers"]["delete"] is True
    assert caps["object_setup"]["correlation-rules"]["list"] is False


def test_xsiam_biocs_and_indicators_supported() -> None:
    caps = profile_capabilities(_profile(Platform.XSIAM))
    assert caps["indicators"]["biocs"]["list"] is True
    assert caps["indicators"]["indicators"]["delete"] is True
    assert caps["system_admin"]["api-keys"]["generate"] is True


def test_xsoar6_no_rbac_or_api_keys() -> None:
    caps = profile_capabilities(_profile(Platform.XSOAR6))
    assert caps["system_admin"]["rbac-users"]["support"] == "unsupported"
    assert caps["system_admin"]["api-keys"]["support"] == "unsupported"


def test_xsoar8_classifier_delete_supported() -> None:
    caps = profile_capabilities(_profile(Platform.XSOAR8))
    assert caps["object_setup"]["classifiers"]["delete"] is True
    assert caps["object_setup"]["preprocess"]["delete"] is True


def test_xsiam_layout_delete_supported() -> None:
    caps = profile_capabilities(_profile(Platform.XSIAM))
    assert caps["object_setup"]["layouts"]["delete"] is True
    assert caps["object_setup"]["classifiers"]["delete"] is False
