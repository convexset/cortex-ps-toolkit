"""Tests for platform admin indicator listing on XSOAR vs Cortex."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cortex_ps_toolkit.credentials import CredentialProfile
from cortex_ps_toolkit.platform_admin.api import list_indicators
from cortex_ps_toolkit.platform_admin.cache import write_cache
from cortex_ps_toolkit.platforms import Platform


def _profile(platform: Platform) -> CredentialProfile:
    return CredentialProfile(
        id="test-id",
        label="indicators",
        slug=f"indicators-{platform.value}",
        url="https://tenant.example.test",
        api_id="42",
        key="secret-key",
        tenant_type=platform,
        verify_ssl=True,
    )


@pytest.mark.parametrize("platform", [Platform.XSOAR6, Platform.XSOAR8])
def test_list_indicators_xsoar_uses_search(platform: Platform) -> None:
    profile = _profile(platform)
    with patch("cortex_ps_toolkit.platform_admin.api.TenantClient") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        client.post_json.return_value = {
            "iocObjects": [{"id": "1", "value": "1.2.3.4", "indicator_type": "IP"}],
        }

        items = list_indicators(profile, limit=50)

    assert len(items) == 1
    assert items[0]["value"] == "1.2.3.4"
    call = client.post_json.call_args
    assert "/indicators/search" in call.args[0]
    assert call.kwargs["payload"] == {"query": "*", "size": 50, "from": 0}


@pytest.mark.parametrize("platform", [Platform.XSIAM, Platform.XDR5])
def test_list_indicators_cortex_uses_public_api(platform: Platform) -> None:
    profile = _profile(platform)
    with patch("cortex_ps_toolkit.platform_admin.api.TenantClient") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        client.post_json.return_value = {
            "objects": [{"indicator_id": "57", "indicator": "evil.example", "module": "XDR IOC"}],
        }

        items = list_indicators(profile)

    assert len(items) == 1
    call = client.post_json.call_args
    assert "public_api/v1/indicators/get" in call.args[0]


def test_write_cache_indicator_summaries_use_value_and_type() -> None:
    profile = _profile(Platform.XSOAR6)
    path = write_cache(profile, "indicators", [
        {"id": "114", "value": "8.8.8.8", "indicator_type": "IP"},
    ])
    payload = path.read_text(encoding="utf-8")
    assert "8.8.8.8" in payload
    assert "IP" in payload
