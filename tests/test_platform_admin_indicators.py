"""Tests for platform admin indicator delete routing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cortex_ps_toolkit.credentials import CredentialProfile
from cortex_ps_toolkit.platform_admin.api import delete_indicators, xsoar_batch_delete_payload
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


def test_xsoar_batch_delete_payload_single_id() -> None:
    payload = xsoar_batch_delete_payload(["114"])
    assert payload["ids"] == ["114"]
    assert payload["doNotWhitelist"] is True
    assert payload["all"] is False
    assert payload["filter"]["query"] == 'id:"114"'
    assert payload["filter"]["size"] == 5


def test_xsoar_batch_delete_payload_multiple_ids() -> None:
    payload = xsoar_batch_delete_payload(["114", "115"])
    assert payload["filter"]["query"] == 'id:"114" or id:"115"'
    assert payload["filter"]["size"] == 5


@pytest.mark.parametrize("platform", [Platform.XSOAR6, Platform.XSOAR8])
def test_delete_indicators_xsoar_uses_batch_delete(platform: Platform) -> None:
    profile = _profile(platform)
    with patch("cortex_ps_toolkit.platform_admin.api.TenantClient") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        client.post_json_with_status.return_value = ({"uppdated": 1}, 200)

        result, status = delete_indicators(profile, ["114"])

    assert status == 200
    assert result == {"uppdated": 1}
    client.post_json_with_status.assert_called_once()
    call = client.post_json_with_status.call_args
    assert call.args[0].endswith("/indicators/batchDelete")
    assert call.kwargs["payload"] == xsoar_batch_delete_payload(["114"])


@pytest.mark.parametrize("platform", [Platform.XSIAM, Platform.XDR5])
def test_delete_indicators_cortex_platform_uses_filter_delete(platform: Platform) -> None:
    profile = _profile(platform)
    rule_ids = ["57", "58"]
    with patch("cortex_ps_toolkit.platform_admin.api.TenantClient") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        client.post_json_with_status.return_value = ({"objects_count": 2}, 200)

        result, status = delete_indicators(profile, rule_ids)

    assert status == 200
    client.post_json_with_status.assert_called_once()
    kwargs = client.post_json_with_status.call_args[1]
    assert kwargs["payload"] == {
        "request_data": {
            "filters": [{"field": "rule_id", "operator": "IN", "value": rule_ids}],
        },
    }
