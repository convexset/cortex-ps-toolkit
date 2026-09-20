"""Low-level automation/script HTTP calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional
from urllib.parse import quote

import yaml

from ..content.yaml_codec import dumps_yaml, loads_yaml
from ..content.zip_payload import (
    decode_zip_yaml_payload,
    insert_failure_items,
    item_name_from_yaml,
    xsiam_content_zip_bytes,
)
from ..core.client import TenantApiError, TenantClient
from ..core.paths import (
    XSOAR_COMPAT_PLATFORMS,
    uses_cortex_platform_content_api,
    xsoar_shaped_path,
)
from ..credentials import CredentialProfile
from ..platforms import Platform, assert_operation_supported


@dataclass(frozen=True)
class ScriptSearchResult:
    scripts: list[dict[str, Any]]
    endpoint: str
    status_code: Optional[int] = None
    warning: Optional[str] = None
    compat_mode: bool = False


def _client(profile: CredentialProfile) -> TenantClient:
    assert_operation_supported("cache.scripts.refresh", profile.tenant_type)
    return TenantClient(profile)


def _uses_compat_content_api(platform: Platform) -> bool:
    return platform in XSOAR_COMPAT_PLATFORMS


def automation_search_url(client: TenantClient) -> str:
    platform = client.profile.tenant_type
    if _uses_compat_content_api(platform):
        return client.xsoar_compat_url("/automation/search")
    return f"{client.profile.host}{xsoar_shaped_path(platform, '/automation/search')}"


def automation_load_url(client: TenantClient, script_id: str) -> str:
    encoded = quote(str(script_id), safe="")
    platform = client.profile.tenant_type
    if _uses_compat_content_api(platform):
        return client.xsoar_compat_url(f"/automation/load/{encoded}")
    return f"{client.profile.host}{xsoar_shaped_path(platform, f'/automation/load/{encoded}')}"


def automation_save_url(client: TenantClient) -> str:
    platform = client.profile.tenant_type
    if uses_cortex_platform_content_api(platform):
        return client.public_api_url("/scripts/insert")
    if platform == Platform.XSOAR6:
        return f"{client.profile.host}{xsoar_shaped_path(platform, '/automation/import')}"
    return f"{client.profile.host}{xsoar_shaped_path(platform, '/automation')}"


def automation_save_json_url(client: TenantClient) -> str:
    """JSON create/update (XSOAR 6/8). Distinct from YAML import on XSOAR 6."""
    platform = client.profile.tenant_type
    return f"{client.profile.host}{xsoar_shaped_path(platform, '/automation')}"


def automation_delete_url(client: TenantClient) -> str:
    platform = client.profile.tenant_type
    if uses_cortex_platform_content_api(platform):
        return client.public_api_url("/scripts/delete")
    if platform == Platform.XSOAR8:
        # Public v1 /automation/delete returns 303 on cloud XSOAR 8; UI uses host-root web-app route.
        return f"{client.profile.host}/xsoar/automation/delete"
    if _uses_compat_content_api(platform):
        return client.xsoar_compat_url("/automation/delete")
    return f"{client.profile.host}{xsoar_shaped_path(platform, '/automation/delete')}"


def _platform_scripts_get(profile: CredentialProfile, *, field: str, value: str) -> dict[str, Any]:
    client = _client(profile)
    payload = {"request_data": {"filter": {"field": field, "value": value}}}
    raw = client.post_bytes(
        client.public_api_url("/scripts/get"),
        action=f"scripts/get field={field}",
        payload=payload,
    )
    yaml_text = decode_zip_yaml_payload(raw, content_kind="script")
    return loads_yaml(yaml_text)


def _parse_script_load_response(data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and isinstance(data.get("script"), dict):
        return dict(data["script"])
    if isinstance(data, dict):
        return dict(data)
    raise ValueError(f"load script returned unexpected shape: {type(data)}")


def _json_or_raw(data: Any) -> dict[str, Any]:
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        return {"status": data}
    return {"raw": data}


def search_scripts(profile: CredentialProfile) -> ScriptSearchResult:
    """Bulk script list via XSOAR-shaped automation/search (incl. XSIAM/XDR/AgentiX compat)."""
    client = _client(profile)
    url = automation_search_url(client)
    compat_mode = _uses_compat_content_api(profile.tenant_type)
    timeout = max(client.timeout, 300.0) if compat_mode else client.timeout
    try:
        data, status = client.post_json_with_status(
            url,
            action="automation search",
            payload={},
            timeout=timeout,
        )
    except TenantApiError as exc:
        if compat_mode:
            return ScriptSearchResult(
                scripts=[],
                endpoint=url,
                status_code=exc.status_code,
                warning=(
                    f"XSOAR compat automation/search unavailable on {profile.tenant_type.value} "
                    f"(HTTP {exc.status_code})."
                ),
                compat_mode=True,
            )
        raise
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected automation search response: {type(data)}")
    scripts = data.get("scripts") or []
    parsed = [item for item in scripts if isinstance(item, dict)]
    return ScriptSearchResult(
        scripts=parsed,
        endpoint=url,
        status_code=status,
        compat_mode=compat_mode,
    )


def _load_script_via_automation_endpoint(client: TenantClient, script_id: str) -> dict[str, Any]:
    """Load one automation script. XSOAR 6/8 and compat tenants use POST on automation/load."""
    url = automation_load_url(client, script_id)
    data = client.post_json(
        url,
        action=f"load script {script_id}",
        payload={},
    )
    return _parse_script_load_response(data)


def get_script(profile: CredentialProfile, script_id: str) -> dict[str, Any]:
    client = _client(profile)
    if uses_cortex_platform_content_api(profile.tenant_type):
        try:
            return _platform_scripts_get(profile, field="id", value=script_id)
        except TenantApiError:
            pass
    try:
        return _load_script_via_automation_endpoint(client, script_id)
    except TenantApiError as exc:
        if uses_cortex_platform_content_api(profile.tenant_type):
            return _platform_scripts_get(profile, field="id", value=script_id)
        if exc.status_code == 405:
            data = client.get_json(
                automation_load_url(client, script_id),
                action=f"load script {script_id} (GET fallback)",
            )
            return _parse_script_load_response(data)
        raise


def get_script_by_name(profile: CredentialProfile, name: str) -> dict[str, Any]:
    if uses_cortex_platform_content_api(profile.tenant_type):
        try:
            return _platform_scripts_get(profile, field="name", value=name)
        except TenantApiError:
            pass

    matches = [
        item
        for item in search_scripts(profile).scripts
        if str(item.get("name") or "") == name
    ]
    if len(matches) == 1:
        script_id = str(matches[0].get("id") or "")
        if script_id:
            return get_script(profile, script_id)
        return dict(matches[0])
    if len(matches) > 1:
        raise ValueError(f"Script name {name!r} is ambiguous ({len(matches)} matches)")
    raise KeyError(f"Script name {name!r} not found")


def get_script_yaml(profile: CredentialProfile, script_id: str) -> str:
    script = get_script(profile, script_id)
    return dumps_yaml(script)


def save_script_json(profile: CredentialProfile, script: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
    """Save one automation script via XSOAR 8 JSON automation endpoint."""
    client = _client(profile)
    payload = {
        "savePassword": bool(str(script.get("pswd") or "").strip()),
        "script": dict(script),
    }
    data, status = client.post_json_with_status(
        automation_save_json_url(client),
        action="automation save json",
        payload=payload,
    )
    return _json_or_raw(data), status


def save_script_yaml(profile: CredentialProfile, yaml_text: str, *, filename: str = "script.yml") -> tuple[dict[str, Any], int]:
    client = _client(profile)
    platform = profile.tenant_type

    if uses_cortex_platform_content_api(platform):
        zip_bytes = xsiam_content_zip_bytes(yaml_text, content_kind="script", filename=filename)
        zip_name = item_name_from_yaml(yaml_text, filename).replace(" ", "_").replace("/", "_") + ".zip"
        data, status = client.post_multipart_with_status(
            automation_save_url(client),
            action="scripts/insert",
            files={"file": (zip_name, zip_bytes, "application/zip")},
        )
        result = _json_or_raw(data)
        failures = insert_failure_items(result)
        if failures:
            detail = "; ".join(
                str(item.get("error") or item.get("message") or item)
                for item in failures
            )
            raise TenantApiError(
                f"scripts/insert failed: {detail}",
                status_code=status,
                body=result,
            )
        return result, status

    if platform == Platform.XSOAR6:
        files = {"file": (filename, yaml_text.encode("utf-8"), "text/yaml")}
        data, status = client.post_multipart_with_status(
            automation_save_url(client),
            action="automation import",
            files=files,
        )
        return _json_or_raw(data), status

    loaded = yaml.safe_load(yaml_text)
    if not isinstance(loaded, dict):
        raise ValueError(f"Script YAML must deserialize to an object: {filename}")
    return save_script_json(profile, loaded)


def delete_script(
    profile: CredentialProfile,
    *,
    script_id: Optional[str] = None,
    name: Optional[str] = None,
) -> tuple[Any, int]:
    if not script_id and not name:
        raise ValueError("delete_script requires script_id or name")

    client = _client(profile)
    resolved_id = script_id
    if not resolved_id:
        found = get_script_by_name(profile, str(name))
        resolved_id = str(found.get("id") or "")
        if not resolved_id:
            raise ValueError(f"Script name {name!r} has no id")

    if uses_cortex_platform_content_api(profile.tenant_type):
        field, value = ("id", resolved_id) if script_id else ("name", str(name))
        payload = {"request_data": {"filter": {"field": field, "value": value}}}
        return client.post_json_with_status(
            automation_delete_url(client),
            action="scripts/delete",
            payload=payload,
        )

    payload = {"script": {"id": resolved_id}}
    return client.post_json_with_status(
        automation_delete_url(client),
        action=f"automation delete {resolved_id}",
        payload=payload,
    )


def cache_entry_from_search(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or ""),
        "modified": item.get("modified"),
        "system": item.get("system") is True,
        "scriptType": item.get("scriptType") or item.get("type"),
        "description": item.get("comment") or item.get("description") or "",
        "version": item.get("version"),
    }
