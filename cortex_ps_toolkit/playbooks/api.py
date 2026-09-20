"""Low-level Playbook HTTP calls."""

from __future__ import annotations

from typing import Any, Mapping, Optional
from urllib.parse import quote

from ..content.yaml_codec import dumps_yaml, loads_yaml
from ..content.zip_payload import (
    decode_zip_yaml_payload,
    insert_failure_items,
    item_name_from_yaml,
    xsiam_content_zip_bytes,
    yaml_to_flat_zip_bytes,
)
from ..core.client import TenantApiError, TenantClient
from ..core.paths import XSOAR_COMPAT_PLATFORMS, uses_cortex_platform_content_api, xsoar_shaped_path
from ..credentials import CredentialProfile
from ..platforms import Platform, assert_operation_supported


def _client(profile: CredentialProfile) -> TenantClient:
    assert_operation_supported("cache.playbooks.refresh", profile.tenant_type)
    return TenantClient(profile)


def playbook_search_url(client: TenantClient) -> str:
    platform = client.profile.tenant_type
    if platform in XSOAR_COMPAT_PLATFORMS:
        return client.xsoar_compat_url("/playbook/search")
    return f"{client.profile.host}{xsoar_shaped_path(platform, '/playbook/search')}"


def playbook_get_url(client: TenantClient, playbook_id: str) -> str:
    encoded = quote(str(playbook_id), safe="")
    return f"{client.profile.host}{xsoar_shaped_path(client.profile.tenant_type, f'/playbook/{encoded}')}"


def playbook_delete_url(client: TenantClient) -> str:
    platform = client.profile.tenant_type
    if uses_cortex_platform_content_api(platform):
        return client.public_api_url("/playbooks/delete")
    if platform == Platform.XSOAR8:
        return f"{client.profile.host}/xsoar/playbook/delete"
    return f"{client.profile.host}{xsoar_shaped_path(platform, '/playbook/delete')}"


def playbook_save_yaml_url(client: TenantClient) -> str:
    platform = client.profile.tenant_type
    if uses_cortex_platform_content_api(platform):
        return client.public_api_url("/playbooks/insert")
    return f"{client.profile.host}{xsoar_shaped_path(platform, '/playbook/save/yaml')}"


def _normalize_playbook(data: Mapping[str, Any]) -> dict[str, Any]:
    if "playbook" in data and isinstance(data["playbook"], dict) and "tasks" not in data:
        return dict(data["playbook"])
    return dict(data)


def _json_or_raw(data: Any, *, status_code: int = 200) -> dict[str, Any]:
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        return {"status": data}
    return {"raw": data}


def _platform_playbooks_get(
    profile: CredentialProfile,
    *,
    field: str,
    value: str,
) -> dict[str, Any]:
    client = _client(profile)
    payload = {"request_data": {"filter": {"field": field, "value": value}}}
    raw = client.post_bytes(
        client.public_api_url("/playbooks/get"),
        action=f"playbooks/get {field}={value}",
        payload=payload,
    )
    yaml_text = decode_zip_yaml_payload(raw, content_kind="playbook")
    return loads_yaml(yaml_text)


def search_playbooks(profile: CredentialProfile, *, query: Optional[str] = None) -> list[dict[str, Any]]:
    client = _client(profile)
    payload: dict[str, Any] = {}
    if query:
        payload["query"] = query
    compat_mode = profile.tenant_type in XSOAR_COMPAT_PLATFORMS
    timeout = max(client.timeout, 300.0) if compat_mode else client.timeout
    data, _status = client.post_json_with_status(
        playbook_search_url(client),
        action="playbook search",
        payload=payload,
        timeout=timeout,
    )
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected playbook search response: {type(data)}")
    playbooks = data.get("playbooks") or []
    return [item for item in playbooks if isinstance(item, dict)]


def get_playbook(profile: CredentialProfile, playbook_id: str) -> dict[str, Any]:
    client = _client(profile)
    if uses_cortex_platform_content_api(profile.tenant_type):
        return _platform_playbooks_get(profile, field="id", value=playbook_id)

    url = playbook_get_url(client, playbook_id)
    try:
        data = client.get_json(url, action=f"get playbook {playbook_id}")
    except TenantApiError as exc:
        if exc.status_code == 404 and profile.tenant_type == Platform.XSOAR6:
            return _get_from_search(client, playbook_id)
        raise
    if not isinstance(data, dict):
        raise ValueError(f"get playbook returned non-object: {type(data)}")
    return _normalize_playbook(data)


def get_playbook_by_name(profile: CredentialProfile, name: str) -> dict[str, Any]:
    if uses_cortex_platform_content_api(profile.tenant_type):
        return _platform_playbooks_get(profile, field="name", value=name)

    results = search_playbooks(profile)
    matches = [item for item in results if str(item.get("name") or "") == name]
    if len(matches) == 1:
        playbook_id = str(matches[0].get("id") or "")
        if playbook_id and "tasks" not in matches[0]:
            return get_playbook(profile, playbook_id)
        return _normalize_playbook(matches[0])
    if len(matches) > 1:
        raise ValueError(f"Playbook name {name!r} is ambiguous ({len(matches)} matches)")
    raise KeyError(f"Playbook name {name!r} not found")


def _get_from_search(client: TenantClient, playbook_id: str) -> dict[str, Any]:
    data, _status = client.post_json_with_status(
        playbook_search_url(client),
        action="playbook search fallback",
        payload=None,
    )
    if not isinstance(data, dict):
        raise ValueError("playbook search fallback returned non-object")
    for item in data.get("playbooks") or []:
        if isinstance(item, dict) and str(item.get("id")) == str(playbook_id):
            return _normalize_playbook(item)
    raise KeyError(f"Playbook {playbook_id!r} not found in search results")


def get_playbook_yaml(profile: CredentialProfile, playbook_id: str) -> str:
    playbook = get_playbook(profile, playbook_id)
    return dumps_yaml(playbook)


def save_playbook_yaml(profile: CredentialProfile, yaml_text: str, *, filename: str = "playbook.yml") -> tuple[dict[str, Any], int]:
    client = _client(profile)
    platform = profile.tenant_type

    if uses_cortex_platform_content_api(platform):
        pack_result, status = _platform_playbook_insert(client, yaml_text, filename)
        return pack_result, status

    files = {"file": (filename, yaml_text.encode("utf-8"), "text/yaml")}
    data, status = client.post_multipart_with_status(
        playbook_save_yaml_url(client),
        action="playbook save yaml",
        files=files,
    )
    return _json_or_raw(data), status


def _platform_playbook_insert(client: TenantClient, yaml_text: str, filename: str) -> tuple[dict[str, Any], int]:
    url = client.public_api_url("/playbooks/insert")

    def _post_zip(label: str, zip_bytes: bytes, zip_name: str) -> tuple[dict[str, Any], int]:
        data, status = client.post_multipart_with_status(
            url,
            action=label,
            files={"file": (zip_name, zip_bytes, "application/zip")},
        )
        return _json_or_raw(data), status

    flat_name = filename.replace(" ", "_").replace("/", "_")
    if not flat_name.lower().endswith(".zip"):
        flat_name = flat_name.rsplit(".", 1)[0] + ".zip"
    flat_bytes = yaml_to_flat_zip_bytes(yaml_text, filename=filename)
    flat_result, flat_status = _post_zip("playbooks/insert flat zip", flat_bytes, flat_name)
    if not insert_failure_items(flat_result):
        flat_result.setdefault("upload_mode", "flat_zip")
        return flat_result, flat_status

    pack_bytes = xsiam_content_zip_bytes(yaml_text, content_kind="playbook", filename=filename)
    pack_name = item_name_from_yaml(yaml_text, filename).replace(" ", "_").replace("/", "_") + ".zip"
    pack_result, pack_status = _post_zip("playbooks/insert pack zip", pack_bytes, pack_name)
    if not insert_failure_items(pack_result):
        pack_result.setdefault("upload_mode", "pack_zip")
        return pack_result, pack_status

    failures = insert_failure_items(flat_result) or insert_failure_items(pack_result)
    detail = "; ".join(
        str(item.get("error") or item.get("message") or item)
        for item in failures
    )
    raise TenantApiError(
        f"playbooks/insert failed: {detail}",
        status_code=pack_status,
        body=pack_result,
    )


def delete_playbook(
    profile: CredentialProfile,
    *,
    playbook_id: Optional[str] = None,
    name: Optional[str] = None,
) -> tuple[Any, int]:
    if not playbook_id and not name:
        raise ValueError("delete_playbook requires playbook_id or name")

    client = _client(profile)
    if uses_cortex_platform_content_api(profile.tenant_type):
        field, value = ("id", playbook_id) if playbook_id else ("name", name)
        payload = {"request_data": {"filter": {"field": field, "value": value}}}
        return client.post_json_with_status(
            playbook_delete_url(client),
            action="playbooks/delete",
            payload=payload,
        )

    resolved_id = playbook_id
    resolved_name = name
    if not resolved_id:
        found = get_playbook_by_name(profile, str(name))
        resolved_id = str(found.get("id") or "")
        resolved_name = resolved_name or str(found.get("name") or "")
        if not resolved_id:
            raise ValueError(f"Playbook name {name!r} has no id")

    payload: dict[str, Any] = {"id": resolved_id}
    if resolved_name:
        payload["name"] = resolved_name
    return client.post_json_with_status(
        playbook_delete_url(client),
        action=f"playbook delete {resolved_id}",
        payload=payload,
    )


def cache_entry_from_search(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or ""),
        "modified": item.get("modified"),
        "system": item.get("system") is True,
        "description": item.get("description") or "",
        "version": item.get("version"),
    }
