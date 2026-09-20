"""Unit tests: API endpoint paths and HTTP methods per platform (no live HTTP).

Covers all lab tenant platform types. XDR 3 path rules are tested separately in
test_compat_paths.py (marked xdr3); there is no live XDR 3 tenant.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cortex_ps_toolkit.core.client import TenantClient
from cortex_ps_toolkit.core.paths import (
    XSOAR_PUBLIC_V1_PREFIX,
    uses_cortex_platform_content_api,
    xsoar_shaped_path,
)
from cortex_ps_toolkit.credentials import CredentialProfile
from cortex_ps_toolkit.platforms import Platform, UnsupportedOperation, assert_operation_supported, get_operation
from cortex_ps_toolkit.integrations import api as integrations_api
from cortex_ps_toolkit.playbooks import api as playbooks_api
from cortex_ps_toolkit.scripts import api as scripts_api

from tests.conftest import LAB_TENANT_CASES

_SCRIPT_ID = "96549dff-30fc-4ee7-8b22-e5d30eded845"
_PLAYBOOK_ID = "11111111-2222-3333-4444-555555555555"


def _profile(platform: Platform) -> CredentialProfile:
    return CredentialProfile(
        id="test-id",
        label="matrix",
        slug=f"matrix-{platform.value}",
        url="https://tenant.example.test",
        api_id="42",
        key="secret-key",
        tenant_type=platform,
        verify_ssl=True,
    )


def _client(platform: Platform) -> TenantClient:
    return TenantClient(_profile(platform))


@pytest.mark.parametrize("slug,platform", LAB_TENANT_CASES, ids=[s for s, _ in LAB_TENANT_CASES])
def test_automation_load_url_per_lab_platform(slug: str, platform: Platform) -> None:
    client = _client(platform)
    url = scripts_api.automation_load_url(client, _SCRIPT_ID)
    assert url.startswith("https://tenant.example.test")
    if platform == Platform.XSOAR6:
        assert url.endswith(f"/automation/load/{_SCRIPT_ID}")
        assert XSOAR_PUBLIC_V1_PREFIX not in url
    else:
        assert f"{XSOAR_PUBLIC_V1_PREFIX}/automation/load/{_SCRIPT_ID}" in url


@pytest.mark.parametrize("slug,platform", LAB_TENANT_CASES, ids=[s for s, _ in LAB_TENANT_CASES])
def test_automation_delete_url_per_lab_platform(slug: str, platform: Platform) -> None:
    client = _client(platform)
    url = scripts_api.automation_delete_url(client)
    if uses_cortex_platform_content_api(platform):
        assert url == "https://tenant.example.test/public_api/v1/scripts/delete"
    elif platform == Platform.XSOAR8:
        assert url == "https://tenant.example.test/xsoar/automation/delete"
    elif platform == Platform.XSOAR6:
        assert url == "https://tenant.example.test/automation/delete"
    else:
        assert url.endswith("/xsoar/public/v1/automation/delete")


@pytest.mark.parametrize("slug,platform", LAB_TENANT_CASES, ids=[s for s, _ in LAB_TENANT_CASES])
def test_automation_search_url_per_lab_platform(slug: str, platform: Platform) -> None:
    client = _client(platform)
    url = scripts_api.automation_search_url(client)
    expected_suffix = xsoar_shaped_path(platform, "/automation/search")
    assert url == f"https://tenant.example.test{expected_suffix}"


@pytest.mark.parametrize("slug,platform", LAB_TENANT_CASES, ids=[s for s, _ in LAB_TENANT_CASES])
def test_playbook_search_url_per_lab_platform(slug: str, platform: Platform) -> None:
    client = _client(platform)
    url = playbooks_api.playbook_search_url(client)
    expected_suffix = xsoar_shaped_path(platform, "/playbook/search")
    assert url == f"https://tenant.example.test{expected_suffix}"


@pytest.mark.parametrize("slug,platform", LAB_TENANT_CASES, ids=[s for s, _ in LAB_TENANT_CASES])
def test_playbook_get_url_per_lab_platform(slug: str, platform: Platform) -> None:
    client = _client(platform)
    url = playbooks_api.playbook_get_url(client, _PLAYBOOK_ID)
    expected_suffix = xsoar_shaped_path(platform, f"/playbook/{_PLAYBOOK_ID}")
    assert url == f"https://tenant.example.test{expected_suffix}"


@pytest.mark.parametrize("slug,platform", LAB_TENANT_CASES, ids=[s for s, _ in LAB_TENANT_CASES])
def test_integration_commands_url_per_lab_platform(slug: str, platform: Platform) -> None:
    client = _client(platform)
    url = integrations_api.integration_commands_url(client)
    expected_suffix = xsoar_shaped_path(platform, "/settings/integration-commands")
    assert url == f"https://tenant.example.test{expected_suffix}"


@pytest.mark.parametrize("slug,platform", LAB_TENANT_CASES, ids=[s for s, _ in LAB_TENANT_CASES])
def test_integration_search_url_per_lab_platform(slug: str, platform: Platform) -> None:
    client = _client(platform)
    url = integrations_api.integration_search_url(client)
    if platform in {Platform.XSIAM, Platform.XDR5, Platform.AGENTIX}:
        assert url.endswith("/xsoar/public/v1/settings/integration/search")
    else:
        expected_suffix = xsoar_shaped_path(platform, "/settings/integration/search")
        assert url == f"https://tenant.example.test{expected_suffix}"


@pytest.mark.parametrize("slug,platform", LAB_TENANT_CASES, ids=[s for s, _ in LAB_TENANT_CASES])
def test_integration_conf_delete_url_per_lab_platform(slug: str, platform: Platform) -> None:
    client = _client(platform)
    url = integrations_api.integration_conf_delete_url(client)
    if platform == Platform.XSOAR6:
        assert url == "https://tenant.example.test/settings/integration-conf/delete"
    else:
        assert url == "https://tenant.example.test/xsoar/settings/integration-conf/delete"


@pytest.mark.parametrize("slug,platform", LAB_TENANT_CASES, ids=[s for s, _ in LAB_TENANT_CASES])
def test_integration_conf_upload_url_per_lab_platform(slug: str, platform: Platform) -> None:
    client = _client(platform)
    url = integrations_api.integration_conf_upload_url(client)
    if platform == Platform.XSOAR6:
        assert url == "https://tenant.example.test/settings/integration-conf/upload"
    else:
        assert url == "https://tenant.example.test/xsoar/settings/integration-conf/upload"


@pytest.mark.parametrize("slug,platform", LAB_TENANT_CASES, ids=[s for s, _ in LAB_TENANT_CASES])
def test_lists_url_per_lab_platform(slug: str, platform: Platform) -> None:
    client = _client(platform)
    assert client.lists_url() == f"https://tenant.example.test{xsoar_shaped_path(platform, '/lists')}"


@patch("cortex_ps_toolkit.scripts.api._client")
@pytest.mark.parametrize("platform", [p for _, p in LAB_TENANT_CASES], ids=[p.value for _, p in LAB_TENANT_CASES])
def test_get_script_uses_post_on_xsoar_platforms(mock_client_factory, platform: Platform) -> None:
    profile = _profile(platform)
    client = MagicMock()
    client.profile = profile
    mock_client_factory.return_value = client

    if uses_cortex_platform_content_api(platform):
        with patch("cortex_ps_toolkit.scripts.api._platform_scripts_get") as mock_platform_get:
            mock_platform_get.return_value = {"id": _SCRIPT_ID, "name": "Demo"}
            scripts_api.get_script(profile, _SCRIPT_ID)
        mock_platform_get.assert_called_once()
        client.post_json.assert_not_called()
    else:
        client.post_json.return_value = {"script": {"id": _SCRIPT_ID, "name": "Demo"}}
        scripts_api.get_script(profile, _SCRIPT_ID)
        client.post_json.assert_called_once()
        client.get_json.assert_not_called()


_XQL_LAB_PLATFORMS = tuple(
    (slug, platform)
    for slug, platform in LAB_TENANT_CASES
    if get_operation("xql.run").is_available(platform)
)


@pytest.mark.parametrize("slug,platform", _XQL_LAB_PLATFORMS, ids=[s for s, _ in _XQL_LAB_PLATFORMS])
def test_xql_start_url_on_supported_lab_platforms(slug: str, platform: Platform) -> None:
    client = _client(platform)
    url = client.public_api_url("/xql/start_xql_query")
    assert url == f"https://tenant.example.test/public_api/v1/xql/start_xql_query"


@pytest.mark.parametrize(
    "platform",
    [Platform.XSOAR6, Platform.XSOAR8],
    ids=["xsoar6", "xsoar8"],
)
def test_xql_run_not_available_on_xsoar(platform: Platform) -> None:
    with pytest.raises(UnsupportedOperation):
        assert_operation_supported("xql.run", platform)


@patch("cortex_ps_toolkit.playbooks.api._client")
@pytest.mark.parametrize("platform", [p for _, p in LAB_TENANT_CASES], ids=[p.value for _, p in LAB_TENANT_CASES])
def test_get_playbook_http_method_per_platform(mock_client_factory, platform: Platform) -> None:
    profile = _profile(platform)
    client = MagicMock()
    client.profile = profile
    mock_client_factory.return_value = client

    if uses_cortex_platform_content_api(platform):
        with patch("cortex_ps_toolkit.playbooks.api._platform_playbooks_get") as mock_platform_get:
            mock_platform_get.return_value = {"id": _PLAYBOOK_ID, "name": "PB", "tasks": {}}
            playbooks_api.get_playbook(profile, _PLAYBOOK_ID)
        mock_platform_get.assert_called_once()
        client.get_json.assert_not_called()
        client.post_bytes.assert_not_called()
    else:
        client.get_json.return_value = {"id": _PLAYBOOK_ID, "name": "PB", "tasks": {}}
        playbooks_api.get_playbook(profile, _PLAYBOOK_ID)
        client.get_json.assert_called_once()
        client.post_bytes.assert_not_called()
