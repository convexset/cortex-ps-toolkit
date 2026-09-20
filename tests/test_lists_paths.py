from __future__ import annotations

from cortex_ps_toolkit.core.client import TenantClient
from cortex_ps_toolkit.credentials import CredentialProfile
from cortex_ps_toolkit.platforms import Platform


def _profile(platform: Platform) -> CredentialProfile:
    return CredentialProfile(
        id="1",
        label="test",
        slug="test",
        url="https://tenant.example.test",
        api_id="99",
        key="secret",
        tenant_type=platform,
    )


def test_lists_urls_xsoar8() -> None:
    client = TenantClient(_profile(Platform.XSOAR8))
    assert client.lists_url() == "https://tenant.example.test/xsoar/public/v1/lists"
    assert client.lists_url("/save") == "https://tenant.example.test/xsoar/public/v1/lists/save"


def test_lists_urls_xsoar6() -> None:
    client = TenantClient(_profile(Platform.XSOAR6))
    assert client.lists_url() == "https://tenant.example.test/lists"
    assert client.lists_url("/delete") == "https://tenant.example.test/lists/delete"


def test_lists_urls_xdr5_and_agentix() -> None:
    for platform in (Platform.XDR5, Platform.AGENTIX):
        client = TenantClient(_profile(platform))
        assert client.lists_url() == "https://tenant.example.test/xsoar/public/v1/lists"
