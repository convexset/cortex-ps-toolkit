from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cortex_ps_toolkit.core.client import TenantApiError
from cortex_ps_toolkit.platforms import Platform
from cortex_ps_toolkit.scripts import api


def _profile(platform: Platform) -> MagicMock:
    profile = MagicMock()
    profile.tenant_type = platform
    profile.host = "https://tenant.example"
    profile.key = "token"
    profile.api_id = None
    profile.verify_ssl = True
    return profile


def _mock_client(profile: MagicMock) -> MagicMock:
    client = MagicMock()
    client.profile = profile
    return client


@patch("cortex_ps_toolkit.scripts.api._client")
def test_get_script_xsoar8_uses_post(mock_client_factory) -> None:
    profile = _profile(Platform.XSOAR8)
    client = _mock_client(profile)
    mock_client_factory.return_value = client
    client.post_json.return_value = {"script": {"id": "sc1", "name": "PrintDebug", "script": "print('x')"}}

    script = api.get_script(profile, "96549dff-30fc-4ee7-8b22-e5d30eded845")

    assert script["name"] == "PrintDebug"
    client.post_json.assert_called_once()
    client.get_json.assert_not_called()


@patch("cortex_ps_toolkit.scripts.api._client")
def test_get_script_xsoar6_uses_post(mock_client_factory) -> None:
    profile = _profile(Platform.XSOAR6)
    client = _mock_client(profile)
    mock_client_factory.return_value = client
    client.post_json.return_value = {"id": "sc1", "name": "PrintDebug", "script": "print('x')"}

    script = api.get_script(profile, "sc1")

    assert script["name"] == "PrintDebug"
    client.post_json.assert_called_once()


@patch("cortex_ps_toolkit.scripts.api._platform_scripts_get")
@patch("cortex_ps_toolkit.scripts.api._client")
def test_get_script_xsiam_uses_scripts_get(mock_client_factory, mock_platform_get) -> None:
    profile = _profile(Platform.XSIAM)
    mock_client_factory.return_value = _mock_client(profile)
    mock_platform_get.return_value = {"id": "sc1", "name": "PrintDebug", "script": "print('x')"}

    script = api.get_script(profile, "sc1")

    assert script["name"] == "PrintDebug"
    mock_platform_get.assert_called_once()
    mock_client_factory.return_value.post_json.assert_not_called()


@patch("cortex_ps_toolkit.scripts.api._client")
def test_get_script_post_405_falls_back_to_get(mock_client_factory) -> None:
    profile = _profile(Platform.XSOAR6)
    client = _mock_client(profile)
    mock_client_factory.return_value = client
    client.post_json.side_effect = TenantApiError("load script failed", status_code=405)
    client.get_json.return_value = {"script": {"id": "sc1", "name": "LegacyLoad"}}

    script = api.get_script(profile, "sc1")

    assert script["name"] == "LegacyLoad"
    client.get_json.assert_called_once()


@patch("cortex_ps_toolkit.scripts.api._client")
def test_delete_script_posts_payload(mock_client_factory) -> None:
    profile = _profile(Platform.XSOAR8)
    client = _mock_client(profile)
    mock_client_factory.return_value = client
    client.post_json_with_status.return_value = ({"ok": True}, 200)

    body, status = api.delete_script(profile, script_id="sc1")

    assert status == 200
    client.post_json_with_status.assert_called_once()
    call = client.post_json_with_status.call_args
    assert call.args[0] == "https://tenant.example/xsoar/automation/delete"
    assert call.kwargs["payload"] == {"script": {"id": "sc1"}}


@patch("cortex_ps_toolkit.scripts.api._client")
def test_delete_script_xsoar6_uses_legacy_automation_delete(mock_client_factory) -> None:
    profile = _profile(Platform.XSOAR6)
    client = _mock_client(profile)
    mock_client_factory.return_value = client
    client.post_json_with_status.return_value = ({"ok": True}, 200)

    api.delete_script(profile, script_id="sc1")

    call = client.post_json_with_status.call_args
    assert call.args[0] == "https://tenant.example/automation/delete"
