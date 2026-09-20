"""Low-level integration settings HTTP calls."""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Optional

from ..core.client import TenantClient
from ..core.paths import xsoar_shaped_path, xsoar_webapp_url
from ..credentials import CredentialProfile
from ..platforms import Platform, assert_operation_supported


@dataclass(frozen=True)
class IntegrationApiResult:
    data: Any
    endpoint: str
    status_code: Optional[int] = None
    warning: Optional[str] = None


def _client(profile: CredentialProfile) -> TenantClient:
    return TenantClient(profile)


def integration_commands_url(client: TenantClient) -> str:
    platform = client.profile.tenant_type
    if platform in {Platform.XSIAM, Platform.XDR3, Platform.XDR5, Platform.AGENTIX}:
        return client.xsoar_compat_url("/settings/integration-commands")
    return f"{client.profile.host}{xsoar_shaped_path(platform, '/settings/integration-commands')}"


def integration_conf_delete_url(client: TenantClient) -> str:
    platform = client.profile.tenant_type
    if platform == Platform.XSOAR6:
        return f"{client.profile.host}{xsoar_shaped_path(platform, '/settings/integration-conf/delete')}"
    return xsoar_webapp_url(client.profile.host, platform, "/settings/integration-conf/delete")


def integration_conf_upload_url(client: TenantClient) -> str:
    platform = client.profile.tenant_type
    if platform == Platform.XSOAR6:
        return f"{client.profile.host}{xsoar_shaped_path(platform, '/settings/integration-conf/upload')}"
    return xsoar_webapp_url(client.profile.host, platform, "/settings/integration-conf/upload")


def integration_search_url(client: TenantClient) -> str:
    platform = client.profile.tenant_type
    if platform in {Platform.XSIAM, Platform.XDR3, Platform.XDR5, Platform.AGENTIX}:
        return client.xsoar_compat_url("/settings/integration/search")
    return f"{client.profile.host}{xsoar_shaped_path(platform, '/settings/integration/search')}"


def tenant_credentials_url(client: TenantClient) -> str:
    platform = client.profile.tenant_type
    if platform in {Platform.XSIAM, Platform.XDR3, Platform.XDR5, Platform.AGENTIX}:
        return client.xsoar_compat_url("/settings/credentials")
    return f"{client.profile.host}{xsoar_shaped_path(platform, '/settings/credentials')}"


def installed_packs_url(client: TenantClient) -> str:
    platform = client.profile.tenant_type
    if platform in {Platform.XSIAM, Platform.XDR3, Platform.XDR5, Platform.AGENTIX}:
        return client.xsoar_compat_url("/contentpacks/metadata/installed")
    return f"{client.profile.host}{xsoar_shaped_path(platform, '/contentpacks/metadata/installed')}"


def fetch_integration_commands(profile: CredentialProfile) -> IntegrationApiResult:
    assert_operation_supported("cache.integrations.commands.refresh", profile.tenant_type)
    client = _client(profile)
    url = integration_commands_url(client)
    data, status = client.get_json_with_status(url, action="integration commands")
    if not isinstance(data, list):
        raise ValueError(f"integration-commands returned {type(data).__name__}, expected list")
    return IntegrationApiResult(data=data, endpoint=url, status_code=status)


def fetch_integration_search(profile: CredentialProfile) -> IntegrationApiResult:
    assert_operation_supported("cache.integrations.instances.refresh", profile.tenant_type)
    client = _client(profile)
    url = integration_search_url(client)
    data, status = client.post_json_with_status(
        url,
        action="integration search",
        payload={},
    )
    if not isinstance(data, dict):
        raise ValueError(f"integration/search returned {type(data).__name__}, expected object")
    return IntegrationApiResult(data=data, endpoint=url, status_code=status)


def fetch_tenant_credentials(
    profile: CredentialProfile,
    *,
    page: int = 0,
    size: int = 500,
) -> IntegrationApiResult:
    assert_operation_supported("cache.credentials.refresh", profile.tenant_type)
    client = _client(profile)
    url = tenant_credentials_url(client)
    data, status = client.post_json_with_status(
        url,
        action="tenant credentials list",
        payload={"page": page, "size": size},
    )
    if not isinstance(data, dict):
        raise ValueError(f"credentials list returned {type(data).__name__}, expected object")
    return IntegrationApiResult(data=data, endpoint=url, status_code=status)


def find_integration_configuration(
    profile: CredentialProfile,
    integration_id: str,
    *,
    search_result: Optional[IntegrationApiResult] = None,
) -> dict[str, Any]:
    """Return the full ModuleConfiguration document for an integration id or name."""
    result = search_result or fetch_integration_search(profile)
    configurations = result.data.get("configurations") if isinstance(result.data, dict) else None
    if not isinstance(configurations, list):
        raise ValueError("integration/search did not return configurations[]")
    needle = str(integration_id)
    for item in configurations:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "") == needle or str(item.get("name") or "") == needle:
            return dict(item)
    raise KeyError(f"integration configuration not found: {integration_id}")


def upload_integration_yaml(
    profile: CredentialProfile,
    yaml_bytes: bytes,
    *,
    filename: str,
) -> IntegrationApiResult:
    """Upload an integration definition YAML via integration-conf/upload."""
    assert_operation_supported("integrations.copy", profile.tenant_type)
    client = _client(profile)
    url = integration_conf_upload_url(client)
    data, status = client.post_multipart_with_status(
        url,
        action="upload integration configuration",
        files={"file": (filename, io.BytesIO(yaml_bytes), "application/octet-stream")},
        timeout=300.0,
    )
    return IntegrationApiResult(data=data, endpoint=url, status_code=status)


def delete_integration_configuration(
    profile: CredentialProfile,
    integration_id: str,
    *,
    configuration: Optional[dict[str, Any]] = None,
) -> IntegrationApiResult:
    """Delete an integration definition via integration-conf/delete (full configuration body)."""
    assert_operation_supported("integrations.delete", profile.tenant_type)
    client = _client(profile)
    document = configuration or find_integration_configuration(profile, integration_id)
    url = integration_conf_delete_url(client)
    data, status = client.post_json_with_status(
        url,
        action="delete integration configuration",
        payload=document,
    )
    return IntegrationApiResult(data=data, endpoint=url, status_code=status)


def fetch_installed_packs(profile: CredentialProfile) -> IntegrationApiResult:
    assert_operation_supported("cache.contentpacks.refresh", profile.tenant_type)
    client = _client(profile)
    url = installed_packs_url(client)
    data, status = client.get_json_with_status(url, action="installed content packs")
    if not isinstance(data, list):
        raise ValueError(f"installed packs returned {type(data).__name__}, expected list")
    return IntegrationApiResult(data=data, endpoint=url, status_code=status)
