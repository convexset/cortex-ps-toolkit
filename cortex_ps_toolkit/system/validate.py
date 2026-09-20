"""Credential validation via platform system-management endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from ..core.client import TenantApiError, TenantClient
from ..credentials import CredentialProfile, get_profile
from ..platforms import Platform, assert_operation_supported

# Doc references:
# - XSOAR 6: https://cortex-docs.paloaltonetworks.com/xsoar-6-api/cortex-xsoar-6.x-apis/system-management
# - XSOAR 8: https://cortex-docs.paloaltonetworks.com/xsoar-8-api/cortex-xsoar-8.x-apis/system-management
# - XSIAM/XDR/AgentiX: https://cortex-docs.paloaltonetworks.com/xsiam-api/cortex-platform/system-management


@dataclass(frozen=True)
class ValidationEndpoint:
    check_id: str
    method: str
    path: str
    summary: str
    payload: Optional[Mapping[str, Any]] = None
    url_builder: str = "public_api"  # public_api | root


def _xsoar6_endpoints() -> tuple[ValidationEndpoint, ...]:
    return (
        ValidationEndpoint("health", "GET", "/health", "Check if Cortex XSOAR server is available", url_builder="root"),
        ValidationEndpoint(
            "health_containers",
            "GET",
            "/health/containers",
            "Get health containers",
            url_builder="root",
        ),
        ValidationEndpoint(
            "docker_images",
            "GET",
            "/settings/docker-images",
            "Get Docker Images",
            url_builder="root",
        ),
        ValidationEndpoint(
            "workers_status",
            "GET",
            "/workers/status",
            "Get workers status",
            url_builder="root",
        ),
    )


def _xsoar8_endpoints() -> tuple[ValidationEndpoint, ...]:
    return (
        ValidationEndpoint(
            "system_health_metrics",
            "POST",
            "/system_diagnostics/data/papi/",
            "Get System Health Metrics",
            payload={},
        ),
        ValidationEndpoint(
            "healthcheck",
            "GET",
            "/healthcheck",
            "System Health Check",
        ),
        ValidationEndpoint(
            "tenant_info",
            "POST",
            "/system/get_tenant_info",
            "Get Tenant Info",
            payload={"request_data": {}},
        ),
    )


def _cortex_platform_endpoints() -> tuple[ValidationEndpoint, ...]:
    return (
        ValidationEndpoint(
            "healthcheck",
            "GET",
            "/healthcheck",
            "System Health Check",
        ),
        ValidationEndpoint(
            "tenant_info",
            "POST",
            "/system/get_tenant_info",
            "Get Tenant Info",
            payload={"request_data": {}},
        ),
    )


VALIDATION_ENDPOINTS: Mapping[Platform, tuple[ValidationEndpoint, ...]] = {
    Platform.XSOAR6: _xsoar6_endpoints(),
    Platform.XSOAR8: _xsoar8_endpoints(),
    Platform.XSIAM: _cortex_platform_endpoints(),
    Platform.XDR3: _cortex_platform_endpoints(),
    Platform.XDR5: _cortex_platform_endpoints(),
    Platform.AGENTIX: _cortex_platform_endpoints(),
}


def _build_url(client: TenantClient, endpoint: ValidationEndpoint) -> str:
    if endpoint.url_builder == "root":
        return client.root_url(endpoint.path)
    return client.public_api_url(endpoint.path)


def _run_endpoint(client: TenantClient, endpoint: ValidationEndpoint) -> dict[str, Any]:
    url = _build_url(client, endpoint)
    method = endpoint.method.upper()
    action = f"{method} {endpoint.path}"
    try:
        if method == "GET":
            body, status_code = client.get_json_with_status(url, action=action)
        else:
            body, status_code = client.post_json_with_status(
                url,
                action=action,
                payload=endpoint.payload or {},
            )
        return {
            "id": endpoint.check_id,
            "method": method,
            "path": endpoint.path,
            "summary": endpoint.summary,
            "ok": True,
            "url": url,
            "status_code": status_code,
            "response": body,
        }
    except TenantApiError as exc:
        result: dict[str, Any] = {
            "id": endpoint.check_id,
            "method": method,
            "path": endpoint.path,
            "summary": endpoint.summary,
            "ok": False,
            "url": url,
            "error": str(exc),
            "status_code": exc.status_code,
        }
        if exc.body is not None:
            result["response"] = exc.body
        return result


def run_credential_validation(profile: CredentialProfile | str) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    assert_operation_supported("credentials.validate", resolved.tenant_type)

    endpoints = VALIDATION_ENDPOINTS.get(resolved.tenant_type)
    if not endpoints:
        raise ValueError(f"No validation endpoints configured for {resolved.tenant_type.value}")

    client = TenantClient(resolved)
    checks = [_run_endpoint(client, endpoint) for endpoint in endpoints]
    failed = [check for check in checks if not check["ok"]]
    return {
        "ok": not failed,
        "profile": resolved.slug,
        "tenant_type": resolved.tenant_type.value,
        "url": resolved.host,
        "checks_passed": len(checks) - len(failed),
        "checks_total": len(checks),
        "checks": checks,
        "doc": resolved.tenant_type.doc_overview_url(),
    }


def validate_profile(slug_or_id: str) -> dict[str, Any]:
    """Validate a credential profile against platform system-management APIs."""
    return run_credential_validation(slug_or_id)
