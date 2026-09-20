#!/usr/bin/env python3
"""Probe XSOAR 6/8 indicator delete: batchDelete variants and public_api delete."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from cortex_ps_toolkit.core.client import TenantClient
from cortex_ps_toolkit.core.paths import xsoar_shaped_url
from cortex_ps_toolkit.credentials import CredentialProfile


def _profile_from_file(path: Path, tenant_type: str) -> CredentialProfile:
    raw = json.loads(path.read_text(encoding="utf-8"))
    slug = f"probe-{tenant_type}-{uuid.uuid4().hex[:6]}"
    return CredentialProfile.from_storage_dict({
        **raw,
        "tenant_type": tenant_type,
        "label": slug,
        "slug": slug,
        "api_id": str(raw.get("id") or ""),
        "verify_ssl": bool(raw.get("verify_ssl", True)),
    })


def _post(client: TenantClient, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.session.post(url, json=payload, timeout=client.timeout)
    body: Any
    try:
        body = response.json()
    except Exception:
        body = response.text[:500]
    return {
        "url": url,
        "status_code": response.status_code,
        "body": body,
    }


def _create_xsoar_indicator(client: TenantClient, profile: CredentialProfile, value: str) -> dict[str, Any]:
    host = profile.host.rstrip("/")
    if profile.tenant_type.value == "xsoar8":
        url = f"{host}/xsoar/public/v1/indicator/create"
    else:
        url = f"{host}/indicator/create"
    payload = {
        "indicator": {
            "value": value,
            "indicator_type": "Domain",
            "score": 2,
            "source": "cptk-probe",
        },
        "manually": True,
    }
    return _post(client, url, payload)


def _search_xsoar_indicator(client: TenantClient, profile: CredentialProfile, value: str) -> dict[str, Any]:
    host = profile.host.rstrip("/")
    url = xsoar_shaped_url(host, profile.tenant_type, "/indicators/search")
    payload = {"query": f'value:"{value}"', "size": 5}
    return _post(client, url, payload)


def _delete_variants(
    client: TenantClient,
    profile: CredentialProfile,
    *,
    indicator_id: str,
    indicator_value: str,
) -> list[dict[str, Any]]:
    host = profile.host.rstrip("/")
    platform = profile.tenant_type.value
    batch_payload = {
        "ids": [indicator_id],
        "doNotWhitelist": True,
        "all": False,
    }
    batch_filter_payload = {
        "doNotWhitelist": True,
        "all": False,
        "filter": {"query": f'value:"{indicator_value}"', "size": 5},
    }
    public_delete_payload = {
        "request_data": {
            "filters": [
                {"field": "indicator", "operator": "EQ", "value": indicator_value},
            ],
        },
    }
    candidates: list[tuple[str, dict[str, Any]]] = []
    if platform == "xsoar8":
        candidates.extend([
            ("xsoar8_batchDelete_ids", f"{host}/xsoar/public/v1/indicators/batchDelete", batch_payload),
            ("xsoar8_batchDelete_filter", f"{host}/xsoar/public/v1/indicators/batchDelete", batch_filter_payload),
            ("xsoar8_public_api_delete", f"{host}/public_api/v1/indicators/delete", public_delete_payload),
            ("xsoar8_root_batchDelete", f"{host}/indicators/batchDelete", batch_payload),
        ])
    else:
        candidates.extend([
            ("xsoar6_batchDelete_ids", f"{host}/indicators/batchDelete", batch_payload),
            ("xsoar6_batchDelete_filter", f"{host}/indicators/batchDelete", batch_filter_payload),
            ("xsoar6_public_api_delete", f"{host}/public_api/v1/indicators/delete", public_delete_payload),
            ("xsoar6_shaped_batchDelete", xsoar_shaped_url(host, profile.tenant_type, "/indicators/batchDelete"), batch_payload),
        ])

    results = []
    for name, url, payload in candidates:
        result = _post(client, url, payload)
        result["variant"] = name
        results.append(result)
    return results


def probe_platform(cred_path: Path, tenant_type: str) -> dict[str, Any]:
    profile = _profile_from_file(cred_path, tenant_type)
    client = TenantClient(profile)
    value = f"cptk-probe-{uuid.uuid4().hex[:10]}.example.test"

    out: dict[str, Any] = {
        "platform": tenant_type,
        "host": profile.host,
        "probe_value": value,
    }

    create = _create_xsoar_indicator(client, profile, value)
    out["create"] = create
    if create["status_code"] not in (200, 201):
        out["error"] = "create failed; skipping delete variants"
        return out

    created = create["body"]
    indicator_id = None
    if isinstance(created, dict):
        indicator_id = (
            created.get("id")
            or (created.get("indicator") or {}).get("id")
            or created.get("indicator_id")
        )
    search = _search_xsoar_indicator(client, profile, value)
    out["search"] = search
    if not indicator_id and isinstance(search.get("body"), dict):
        iocs = search["body"].get("iocObjects") or []
        if iocs and isinstance(iocs[0], dict):
            indicator_id = iocs[0].get("id")

    out["indicator_id"] = indicator_id
    if not indicator_id:
        out["error"] = "could not resolve indicator id after create"
        return out

    out["delete_attempts"] = _delete_variants(
        client,
        profile,
        indicator_id=str(indicator_id),
        indicator_value=value,
    )

    verify = _search_xsoar_indicator(client, profile, value)
    out["verify_search_after_delete"] = verify
    if isinstance(verify.get("body"), dict):
        remaining = verify["body"].get("total") or len(verify["body"].get("iocObjects") or [])
        out["remaining_after_delete"] = remaining
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xsoar6-creds", default="/Users/weichen/Downloads/dev/bay/personal-xsoar6-credentials.json")
    parser.add_argument("--xsoar8-creds", default="/Users/weichen/Downloads/dev/bay/lab-xsoar-credentials.json")
    parser.add_argument("--output", default="/tmp/xsoar-indicator-delete-probe.json")
    args = parser.parse_args(argv)

    results: dict[str, Any] = {}
    x6 = Path(args.xsoar6_creds)
    x8 = Path(args.xsoar8_creds)
    if x6.exists():
        results["xsoar6"] = probe_platform(x6, "xsoar6")
    else:
        results["xsoar6"] = {"skipped": True, "reason": f"missing {x6}"}
    if x8.exists():
        results["xsoar8"] = probe_platform(x8, "xsoar8")
    else:
        results["xsoar8"] = {"skipped": True, "reason": f"missing {x8}"}

    out = Path(args.output)
    out.write_text(json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
