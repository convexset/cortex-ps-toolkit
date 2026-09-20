from __future__ import annotations

from pathlib import Path

import pytest
import requests_mock

from cortex_ps_toolkit.credentials import create_profile_from_input
from cortex_ps_toolkit.credentials_validate import validate_profile
from cortex_ps_toolkit.platforms import Platform


def _seed_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, tenant_type: str, host: str) -> str:
    dest = tmp_path / "credentials.json"
    monkeypatch.setattr("cortex_ps_toolkit.credentials.credentials_collection_path", lambda: dest)
    profile = create_profile_from_input({
        "label": f"Validate {tenant_type}",
        "slug": f"validate-{tenant_type}",
        "url": host,
        "key": "secret-key",
        "tenant_type": tenant_type,
        "api_id": "99",
    })
    return profile.slug


def test_validate_xsoar6_runs_all_system_management_gets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = "https://xsoar6.example.test"
    slug = _seed_profile(tmp_path, monkeypatch, tenant_type="xsoar6", host=host)

    with requests_mock.Mocker() as mock:
        mock.get(f"{host}/health", json="OK")
        mock.get(f"{host}/health/containers", json={"all": 3, "running": 2, "inactive": 1})
        mock.get(f"{host}/settings/docker-images", json={"images": []})
        mock.get(f"{host}/workers/status", json={"Name": "workers", "Total": 4})
        result = validate_profile(slug)

    assert result["ok"] is True
    assert result["checks_total"] == 4
    assert result["checks_passed"] == 4
    assert [check["path"] for check in result["checks"]] == [
        "/health",
        "/health/containers",
        "/settings/docker-images",
        "/workers/status",
    ]
    containers = next(check for check in result["checks"] if check["id"] == "health_containers")
    assert containers["response"] == {"all": 3, "running": 2, "inactive": 1}
    assert containers["status_code"] == 200


def test_validate_xsoar8_system_management_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host = "https://xsoar8.example.test"
    slug = _seed_profile(tmp_path, monkeypatch, tenant_type="xsoar8", host=host)

    with requests_mock.Mocker() as mock:
        mock.post(
            f"{host}/public_api/v1/system_diagnostics/data/papi/",
            json={"reply": {"results": []}},
        )
        mock.get(f"{host}/public_api/v1/healthcheck", json={"status": "OK"})
        mock.post(
            f"{host}/public_api/v1/system/get_tenant_info",
            json={"reply": {"purchased_xsiam_premium": {"users": 1}}},
        )
        result = validate_profile(slug)

    assert result["ok"] is True
    assert result["checks_total"] == 3
    assert {check["id"] for check in result["checks"]} == {
        "system_health_metrics",
        "healthcheck",
        "tenant_info",
    }


@pytest.mark.parametrize("tenant_type", ["xsiam", "xdr3", "xdr5", "agentix"])
def test_validate_cortex_platform_health_and_tenant_info(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tenant_type: str,
) -> None:
    host = f"https://{tenant_type}.example.test"
    slug = _seed_profile(tmp_path, monkeypatch, tenant_type=tenant_type, host=host)

    with requests_mock.Mocker() as mock:
        mock.get(f"{host}/public_api/v1/healthcheck", json={"status": "OK"})
        mock.post(
            f"{host}/public_api/v1/system/get_tenant_info",
            json={"reply": {"purchased_xsiam_premium": {"users": 1}}},
        )
        result = validate_profile(slug)

    assert result["ok"] is True
    assert result["checks_total"] == 2
    assert result["tenant_type"] == tenant_type
    assert {check["id"] for check in result["checks"]} == {"healthcheck", "tenant_info"}


def test_validate_reports_partial_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host = "https://xsoar6.example.test"
    slug = _seed_profile(tmp_path, monkeypatch, tenant_type="xsoar6", host=host)

    with requests_mock.Mocker() as mock:
        mock.get(f"{host}/health", json="OK")
        mock.get(f"{host}/health/containers", status_code=403, json={"error": "forbidden"})
        mock.get(f"{host}/settings/docker-images", json={"images": []})
        mock.get(f"{host}/workers/status", json={"Name": "workers", "Total": 1})
        result = validate_profile(slug)

    assert result["ok"] is False
    assert result["checks_passed"] == 3
    failed = [check for check in result["checks"] if not check["ok"]]
    assert len(failed) == 1
    assert failed[0]["id"] == "health_containers"
    assert failed[0]["status_code"] == 403
    assert failed[0]["response"] == {"error": "forbidden"}
