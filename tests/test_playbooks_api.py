from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.platforms import Platform
from cortex_ps_toolkit.playbooks import api


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


@patch("cortex_ps_toolkit.playbooks.api._client")
def test_get_playbook_xsoar8_uses_get(mock_client_factory) -> None:
    profile = _profile(Platform.XSOAR8)
    client = _mock_client(profile)
    mock_client_factory.return_value = client
    client.get_json.return_value = {"id": "pb1", "name": "Main PB", "tasks": {}}

    playbook = api.get_playbook(profile, "pb1")

    assert playbook["name"] == "Main PB"
    client.get_json.assert_called_once()
    client.post_json.assert_not_called()


@patch("cortex_ps_toolkit.playbooks.api.decode_zip_yaml_payload")
@patch("cortex_ps_toolkit.playbooks.api._client")
def test_get_playbook_xsiam_uses_post_get(mock_client_factory, mock_decode) -> None:
    profile = _profile(Platform.XSIAM)
    client = _mock_client(profile)
    mock_client_factory.return_value = client
    client.post_bytes.return_value = b"zip-bytes"
    mock_decode.return_value = "name: Main PB\nid: pb1\n"

    with patch("cortex_ps_toolkit.playbooks.api.loads_yaml", return_value={"id": "pb1", "name": "Main PB"}):
        playbook = api.get_playbook(profile, "pb1")

    assert playbook["name"] == "Main PB"
    client.post_bytes.assert_called_once()
    client.get_json.assert_not_called()


@patch("cortex_ps_toolkit.playbooks.api._client")
def test_delete_playbook_xsoar8_posts_id(mock_client_factory) -> None:
    profile = _profile(Platform.XSOAR8)
    client = _mock_client(profile)
    mock_client_factory.return_value = client
    client.post_json_with_status.return_value = ({"ok": True}, 200)

    body, status = api.delete_playbook(profile, playbook_id="pb1")

    assert status == 200
    client.post_json_with_status.assert_called_once()
