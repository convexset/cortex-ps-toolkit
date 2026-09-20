"""Tests for integration settings API helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.integrations import api as integrations_api
from cortex_ps_toolkit.platforms import Platform


def test_find_integration_configuration_by_id() -> None:
    search = integrations_api.IntegrationApiResult(
        data={
            "configurations": [
                {"id": "alpha", "name": "Alpha"},
                {"id": "beta", "name": "Beta"},
            ],
        },
        endpoint="https://example.test/search",
    )
    found = integrations_api.find_integration_configuration(
        MagicMock(),
        "beta",
        search_result=search,
    )
    assert found["name"] == "Beta"


@patch("cortex_ps_toolkit.integrations.api.find_integration_configuration")
@patch("cortex_ps_toolkit.integrations.api._client")
def test_delete_integration_configuration_posts_full_document(
    mock_client_factory,
    mock_find,
) -> None:
    profile = MagicMock()
    profile.tenant_type = Platform.XSOAR8
    client = MagicMock()
    client.profile = profile
    client.profile.host = "https://tenant.example.test"
    mock_client_factory.return_value = client
    document = {"id": "SampleMirroringIntegration", "name": "SampleMirroringIntegration"}
    mock_find.return_value = document
    client.post_json_with_status.return_value = ({}, 200)

    result = integrations_api.delete_integration_configuration(profile, "SampleMirroringIntegration")

    mock_find.assert_called_once_with(profile, "SampleMirroringIntegration")
    client.post_json_with_status.assert_called_once()
    call = client.post_json_with_status.call_args
    assert call.kwargs["payload"] == document
    assert result.status_code == 200
