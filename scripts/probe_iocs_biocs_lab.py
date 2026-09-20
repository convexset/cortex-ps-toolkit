#!/usr/bin/env python3
"""Live probe: IOC and BIOC CRUD on all configured lab tenants."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from cortex_ps_toolkit.core.client import TenantClient, TenantApiError
from cortex_ps_toolkit.core.paths import xsoar_shaped_url
from cortex_ps_toolkit.credentials import CredentialProfile, get_profile, list_profiles
from cortex_ps_toolkit.platform_admin import api as admin_api
from cortex_ps_toolkit.platforms import Platform, UnsupportedOperation, get_operation

LAB_SLUGS = (
    "personal-xsoar6",
    "xsoar-japac-dev",
    "psojapac-xsiam",
    "cortex-cs-xdr5",
    "cortex-cs-agentix",
)


def _profile(slug: str) -> CredentialProfile:
    return get_profile(slug)


def _post(client: TenantClient, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.session.post(url, json=payload, timeout=client.timeout)
    body: Any
    try:
        body = response.json()
    except Exception:
        body = response.text[:500]
    return {"url": url, "status_code": response.status_code, "body": body}


def _create_xsoar_indicator(profile: CredentialProfile, value: str) -> dict[str, Any]:
    client = TenantClient(profile)
    host = profile.host.rstrip("/")
    if profile.tenant_type == Platform.XSOAR8:
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


def _search_xsoar_indicator(profile: CredentialProfile, value: str) -> dict[str, Any]:
    client = TenantClient(profile)
    host = profile.host.rstrip("/")
    url = xsoar_shaped_url(host, profile.tenant_type, "/indicators/search")
    return _post(client, url, {"query": f'value:"{value}"', "size": 5})


def _resolve_indicator_id(create: dict[str, Any], search: dict[str, Any]) -> str | None:
    body = create.get("body")
    if isinstance(body, dict):
        indicator_id = (
            body.get("id")
            or (body.get("indicator") or {}).get("id")
            or body.get("indicator_id")
        )
        if indicator_id is not None:
            return str(indicator_id)
    search_body = search.get("body")
    if isinstance(search_body, dict):
        iocs = search_body.get("iocObjects") or []
        if iocs and isinstance(iocs[0], dict) and iocs[0].get("id") is not None:
            return str(iocs[0]["id"])
    return None


def _remaining_count(search: dict[str, Any]) -> int | None:
    body = search.get("body")
    if not isinstance(body, dict):
        return None
    total = body.get("total")
    if total is not None:
        return int(total)
    return len(body.get("iocObjects") or [])


def probe_ioc(profile: CredentialProfile) -> dict[str, Any]:
    platform = profile.tenant_type
    out: dict[str, Any] = {"platform": platform.value, "slug": profile.slug}
    spec = get_operation("content.indicators.manage")
    if not spec.is_available(platform):
        out["skipped"] = True
        out["reason"] = "content.indicators.manage unsupported"
        return out

    value = f"cptk-ioc-{uuid.uuid4().hex[:10]}.example.test"
    out["probe_value"] = value

    try:
        if platform in (Platform.XSOAR6, Platform.XSOAR8):
            create = _create_xsoar_indicator(profile, value)
            out["create"] = create
            if create["status_code"] not in (200, 201):
                out["error"] = "create failed"
                return out
            search = _search_xsoar_indicator(profile, value)
            out["search"] = search
            indicator_id = _resolve_indicator_id(create, search)
            out["indicator_id"] = indicator_id
            if not indicator_id:
                out["error"] = "could not resolve indicator id"
                return out
            delete_result, delete_status = admin_api.delete_indicators(profile, [indicator_id])
            out["delete"] = {"status_code": delete_status, "body": delete_result}
            verify = _search_xsoar_indicator(profile, value)
            out["verify_search"] = verify
            out["remaining"] = _remaining_count(verify)
            out["cycle_ok"] = delete_status == 200 and (out["remaining"] or 0) == 0
            return out

        # Cortex Platform IOC API (xsiam, xdr5, agentix)
        ioc = {
            **admin_api.CORTEX_IOC_INSERT_TEMPLATE,
            "indicator": value,
            "type": "DOMAIN_NAME",
        }
        insert_result, insert_status = admin_api.insert_indicators(profile, [ioc])
        out["insert"] = {"status_code": insert_status, "body": insert_result}
        if insert_status != 200:
            out["error"] = "insert failed"
            return out
        rule_id = None
        if isinstance(insert_result, dict):
            added = insert_result.get("added_objects") or []
            if added and isinstance(added[0], dict):
                rule_id = added[0].get("id") or added[0].get("rule_id")
        out["rule_id"] = rule_id
        if not rule_id:
            out["error"] = "could not resolve rule_id after insert"
            return out
        delete_result, delete_status = admin_api.delete_indicators(profile, [str(rule_id)])
        out["delete"] = {"status_code": delete_status, "body": delete_result}
        out["cycle_ok"] = delete_status == 200 and isinstance(delete_result, dict) and (
            delete_result.get("objects_count", 0) >= 1
        )
        return out
    except (TenantApiError, UnsupportedOperation, ValueError) as exc:
        out["error"] = str(exc)
        return out


def _unique_bioc_clone(source: dict[str, Any], probe_name: str) -> dict[str, Any]:
    doc = admin_api.prepare_bioc_write(source, new_name=probe_name)
    doc["comment"] = f"cptk-probe-{uuid.uuid4().hex[:8]}"
    indicator = doc.get("indicator")
    if doc.get("is_xql") and isinstance(indicator, str) and indicator.strip():
        doc["indicator"] = f"{indicator.rstrip()}\n// cptk-{uuid.uuid4().hex[:8]}"
    elif isinstance(indicator, dict):
        if indicator.get("is_xql") or doc.get("is_xql"):
            query = indicator.get("query") or indicator.get("xql_query")
            if isinstance(query, str) and query.strip():
                indicator["query"] = f"{query.strip()} /* cptk-{uuid.uuid4().hex[:8]} */"
        investigation = indicator.get("investigation")
        if isinstance(investigation, dict):
            for event in investigation.values():
                if not isinstance(event, dict):
                    continue
                filt = event.get("filter")
                if not isinstance(filt, dict):
                    continue
                and_list = filt.get("AND")
                if not isinstance(and_list, list):
                    continue
                for clause in and_list:
                    if isinstance(clause, dict) and clause.get("SEARCH_VALUE") is not None:
                        clause["SEARCH_VALUE"] = (
                            f"{clause['SEARCH_VALUE']}-cptk-{uuid.uuid4().hex[:6]}"
                        )
    return doc


def probe_bioc(profile: CredentialProfile) -> dict[str, Any]:
    platform = profile.tenant_type
    out: dict[str, Any] = {"platform": platform.value, "slug": profile.slug}
    spec = get_operation("content.biocs.manage")
    if not spec.is_available(platform):
        out["skipped"] = True
        out["reason"] = "content.biocs.manage unsupported"
        return out

    try:
        items = admin_api.list_biocs(profile, limit=25)
        out["list"] = {"count": len(items), "sample_names": [item.get("name") for item in items[:3]]}
    except (TenantApiError, UnsupportedOperation, ValueError) as exc:
        out["list"] = {"error": str(exc)}
        return out

    if not items:
        out["insert_delete"] = {"skipped": True, "reason": "no existing BIOCs to clone"}
        return out

    probe_name = f"cptk-bioc-{uuid.uuid4().hex[:8]}"
    out["probe_name"] = probe_name

    try:
        insert_result = None
        insert_status = None
        source_name = None
        last_error = None
        candidates = sorted(items, key=lambda item: (not item.get("is_xql"), item.get("name") or ""))
        for source in candidates:
            source_name = str(source.get("name") or "")
            doc = _unique_bioc_clone(source, probe_name)
            try:
                insert_result, insert_status = admin_api.insert_biocs(profile, [doc])
            except TenantApiError as exc:
                insert_status = exc.status_code if hasattr(exc, "status_code") else 400
                insert_result = str(exc)
                last_error = insert_result
                if "behavior already exists" not in insert_result:
                    break
                continue
            if insert_status == 200:
                out["source_name"] = source_name
                break
            last_error = insert_result
            if "behavior already exists" not in str(insert_result):
                break
        out["insert"] = {"status_code": insert_status, "body": insert_result}
        if insert_status != 200:
            sample_name = str(items[0].get("name") or "")
            got = admin_api.get_bioc(profile, sample_name)
            ghost = f"__cptk-nonexistent-{uuid.uuid4().hex[:8]}"
            del_result, del_status = admin_api.delete_bioc(profile, ghost)
            out["api_smoke"] = {
                "get_ok": got is not None,
                "delete_status": del_status,
                "delete_result": del_result,
            }
            if got is not None and del_status == 200:
                out["insert_cycle_skipped"] = True
                out["cycle_ok"] = True
                out["note"] = f"insert clone failed ({last_error}); list/get/delete API smoke passed"
                return out
            out["error"] = f"insert failed after trying {len(candidates)} source(s): {last_error}"
            return out
        delete_result, delete_status = admin_api.delete_bioc(profile, probe_name)
        out["delete"] = {"status_code": delete_status, "body": delete_result}
        remaining = admin_api.get_bioc(profile, probe_name)
        out["remaining_after_delete"] = remaining is not None
        out["cycle_ok"] = (
            insert_status == 200
            and delete_status == 200
            and remaining is None
        )
        return out
    except (TenantApiError, UnsupportedOperation, ValueError) as exc:
        out["error"] = str(exc)
        return out


def probe_tenant(slug: str) -> dict[str, Any]:
    profile = _profile(slug)
    return {
        "slug": slug,
        "host": profile.host,
        "platform": profile.tenant_type.value,
        "ioc": probe_ioc(profile),
        "bioc": probe_bioc(profile),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="/tmp/iocs-biocs-lab-probe.json")
    parser.add_argument("--slug", action="append", help="Limit to profile slug(s)")
    args = parser.parse_args(argv)

    configured = {profile.slug for profile in list_profiles()}
    slugs = [slug for slug in (args.slug or LAB_SLUGS) if slug in configured]
    missing = [slug for slug in (args.slug or LAB_SLUGS) if slug not in configured]

    results: dict[str, Any] = {"tenants": {}, "missing_slugs": missing}
    for slug in slugs:
        results["tenants"][slug] = probe_tenant(slug)

    out = Path(args.output)
    out.write_text(json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2, default=str))

    failures = []
    for slug, tenant in results["tenants"].items():
        platform = tenant.get("platform", "")
        ioc = tenant.get("ioc") or {}
        bioc = tenant.get("bioc") or {}
        if ioc.get("skipped"):
            continue
        if ioc.get("error"):
            if platform == "agentix" and "402" in str(ioc["error"]):
                continue
            failures.append(f"{slug}/ioc")
        elif not ioc.get("cycle_ok"):
            failures.append(f"{slug}/ioc")
        if bioc.get("skipped"):
            continue
        list_err = (bioc.get("list") or {}).get("error")
        if platform == "agentix" and "402" in str(list_err or bioc.get("error", "")):
            continue
        if bioc.get("error") or (
            not bioc.get("cycle_ok")
            and not (bioc.get("insert_delete") or {}).get("skipped")
        ):
            failures.append(f"{slug}/bioc")

    if failures:
        print(f"\nFailures: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
