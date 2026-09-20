from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.core.client import TenantApiError
from cortex_ps_toolkit.platforms import Platform
from cortex_ps_toolkit.scripts import api
from cortex_ps_toolkit.scripts.service import refresh_scripts_cache


def _profile(platform: Platform) -> MagicMock:
    profile = MagicMock()
    profile.slug = "lab"
    profile.tenant_type = platform
    profile.cache_key = "lab-key"
    return profile


@patch("cortex_ps_toolkit.scripts.api._client")
def test_search_scripts_compat_success(mock_client_factory: MagicMock) -> None:
    client = MagicMock()
    client.timeout = 120.0
    client.profile = _profile(Platform.XSIAM)
    client.xsoar_compat_url.return_value = "https://tenant/xsoar/public/v1/automation/search"
    client.post_json_with_status.return_value = (
        {"scripts": [{"id": "1", "name": "PrintDebug"}]},
        200,
    )
    mock_client_factory.return_value = client

    result = api.search_scripts(client.profile)
    assert result.compat_mode is True
    assert len(result.scripts) == 1
    assert result.warning is None
    client.xsoar_compat_url.assert_called_with("/automation/search")


@patch("cortex_ps_toolkit.scripts.api._client")
def test_search_scripts_compat_failure_returns_warning(mock_client_factory: MagicMock) -> None:
    client = MagicMock()
    client.timeout = 120.0
    client.profile = _profile(Platform.XDR5)
    client.xsoar_compat_url.return_value = "https://tenant/xsoar/public/v1/automation/search"
    client.post_json_with_status.side_effect = TenantApiError("nope", status_code=404)
    mock_client_factory.return_value = client

    result = api.search_scripts(client.profile)
    assert result.scripts == []
    assert result.warning is not None
    assert "404" in result.warning


@patch("cortex_ps_toolkit.scripts.service.write_scripts_cache")
@patch("cortex_ps_toolkit.scripts.service.load_scripts_index")
@patch("cortex_ps_toolkit.scripts.api.search_scripts")
@patch("cortex_ps_toolkit.scripts.service.get_profile")
def test_refresh_preserves_cache_when_compat_search_fails(
    mock_get_profile: MagicMock,
    mock_search: MagicMock,
    mock_load_index: MagicMock,
    mock_write_cache: MagicMock,
) -> None:
    profile = _profile(Platform.XSIAM)
    mock_get_profile.return_value = profile
    mock_search.return_value = api.ScriptSearchResult(
        scripts=[],
        endpoint="https://tenant/xsoar/public/v1/automation/search",
        status_code=404,
        warning="XSOAR compat automation/search unavailable on xsiam (HTTP 404).",
        compat_mode=True,
    )
    mock_load_index.return_value = {
        "refreshed_at": "2026-01-01T00:00:00Z",
        "scripts": [{"id": "1", "name": "Existing"}],
    }

    result = refresh_scripts_cache("lab")
    assert result["cache_preserved"] is True
    assert result["count"] == 1
    mock_write_cache.assert_not_called()
