"""Tests for correlation rule listing pagination."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.credentials import CredentialProfile
from cortex_ps_toolkit.platform_admin.api import CORTEX_SEARCH_PAGE_SIZE, list_correlation_rules
from cortex_ps_toolkit.platforms import Platform


def _profile() -> CredentialProfile:
    return CredentialProfile(
        id="test-id",
        label="corr",
        slug="corr-xsiam",
        url="https://tenant.example.test",
        api_id="42",
        key="secret-key",
        tenant_type=Platform.XSIAM,
        verify_ssl=True,
    )


@patch("cortex_ps_toolkit.platform_admin.api.TenantClient")
def test_list_correlation_rules_pages_at_100(mock_cls: MagicMock) -> None:
    profile = _profile()
    client = MagicMock()
    mock_cls.return_value = client
    first_batch = [{"alert_name": f"Rule-{index}"} for index in range(CORTEX_SEARCH_PAGE_SIZE)]
    second_batch = [{"alert_name": "Rule-last"}]
    client.post_json.side_effect = [
        {"objects": first_batch},
        {"objects": second_batch},
    ]

    items = list_correlation_rules(profile, limit=500)

    assert len(items) == CORTEX_SEARCH_PAGE_SIZE + 1
    assert client.post_json.call_count == 2
    first_payload = client.post_json.call_args_list[0].kwargs["payload"]["request_data"]
    second_payload = client.post_json.call_args_list[1].kwargs["payload"]["request_data"]
    assert first_payload["search_from"] == 0
    assert first_payload["search_to"] == CORTEX_SEARCH_PAGE_SIZE
    assert second_payload["search_from"] == CORTEX_SEARCH_PAGE_SIZE
    assert second_payload["search_to"] == CORTEX_SEARCH_PAGE_SIZE * 2
