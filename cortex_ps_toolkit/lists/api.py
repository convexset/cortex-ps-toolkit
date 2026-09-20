"""Low-level Lists HTTP calls."""

from __future__ import annotations

from typing import Any, Mapping, Optional
from urllib.parse import quote

from ..core.client import TenantClient
from ..credentials import CredentialProfile
from ..platforms import Platform, assert_operation_supported


def _client(profile: CredentialProfile) -> TenantClient:
    assert_operation_supported("content.lists.manage", profile.tenant_type)
    return TenantClient(profile)


def fetch_all_lists(profile: CredentialProfile) -> list[dict[str, Any]]:
    client = _client(profile)
    data = client.get_json(client.lists_url(), action="get all lists")
    if data is None:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        items = data.get("lists") or data.get("data")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    raise ValueError(f"Unexpected lists response shape: {type(data)}")


def download_list_data(profile: CredentialProfile, list_id: str) -> Any:
    client = _client(profile)
    encoded = quote(str(list_id), safe="")
    url = client.lists_url(f"/download/{encoded}")
    return client.get_json(url, action=f"download list {list_id}")


def save_list_payload(profile: CredentialProfile, payload: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
    client = _client(profile)
    data, status_code = client.post_json_with_status(
        client.lists_url("/save"),
        action="save list",
        payload=dict(payload),
    )
    if not isinstance(data, dict):
        raise ValueError(f"save list returned non-object: {type(data)}")
    return data, status_code


def delete_list_by_id(profile: CredentialProfile, list_id: str) -> tuple[Any, int]:
    client = _client(profile)
    return client.post_json_with_status(
        client.lists_url("/delete"),
        action=f"delete list {list_id}",
        payload={"id": list_id},
    )


def build_new_list_payload(
    *,
    name: str,
    data: str,
    list_type: str = "plain_text",
    description: str = "",
    all_read: bool = True,
    all_read_write: bool = True,
) -> dict[str, Any]:
    return {
        "name": name,
        "data": data,
        "type": list_type,
        "description": description,
        "allRead": all_read,
        "allReadWrite": all_read_write,
        "shouldCommit": False,
        "shouldPublish": False,
    }


def build_update_list_payload(existing: Mapping[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    merged.update(updates)
    required = ("id", "version", "name", "data", "type")
    missing: list[str] = []
    for field in required:
        if field not in merged or merged[field] is None:
            missing.append(field)
        elif field != "data" and not merged.get(field) and merged.get(field) != 0:
            missing.append(field)
    if missing:
        raise ValueError(f"List update missing required fields: {missing}")
    return {
        "id": merged["id"],
        "version": merged["version"],
        "name": merged["name"],
        "data": merged["data"],
        "type": merged["type"],
        "description": merged.get("description") or "",
        "allRead": merged.get("allRead", True),
        "allReadWrite": merged.get("allReadWrite", True),
        "shouldCommit": False,
        "shouldPublish": False,
    }
