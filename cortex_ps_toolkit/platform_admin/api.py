"""Tenant HTTP for platform administration APIs."""

from __future__ import annotations

from typing import Any, Optional

from ..core.client import TenantClient
from ..core.paths import (
    xsoar_shaped_url,
    api_keys_delete_url,
    api_keys_generate_url,
    api_keys_get_url,
    biocs_delete_url,
    biocs_get_url,
    biocs_insert_url,
    correlations_delete_url,
    correlations_get_url,
    correlations_insert_url,
    indicators_batch_delete_url,
    indicators_delete_url,
    indicators_get_url,
    indicators_insert_url,
    rbac_get_roles_url,
    rbac_get_user_group_url,
    rbac_get_users_url,
    rbac_set_user_role_url,
)
from ..credentials import CredentialProfile
from ..platforms import Platform, assert_operation_supported
from .types import ADMIN_SECTIONS, OPERATION_BY_SECTION, AdminSection

RBAC_NAME_BATCH_SIZE = 20
CORTEX_SEARCH_PAGE_SIZE = 100


def _request_data(payload: dict[str, Any]) -> dict[str, Any]:
    return {"request_data": payload}


def _flatten_rbac_reply(data: dict[str, Any]) -> list[dict[str, Any]]:
    reply = data.get("reply") or []
    flat: list[dict[str, Any]] = []
    if isinstance(reply, list):
        for item in reply:
            if isinstance(item, dict):
                flat.append(item)
            elif isinstance(item, list):
                flat.extend(entry for entry in item if isinstance(entry, dict))
    return flat


def _batch_names(names: list[str], *, size: int = RBAC_NAME_BATCH_SIZE) -> list[list[str]]:
    return [names[index:index + size] for index in range(0, len(names), size)]


def _distinct_user_role_names(users: list[dict[str, Any]]) -> list[str]:
    role_names = {
        str(user.get("role_name") or user.get("role") or "")
        for user in users
        if user.get("role_name") or user.get("role")
    }
    return sorted(name for name in role_names if name)


def _distinct_user_group_names(users: list[dict[str, Any]]) -> list[str]:
    group_names: set[str] = set()
    for user in users:
        groups = user.get("groups")
        if isinstance(groups, list):
            group_names.update(str(group) for group in groups if group)
        elif groups:
            group_names.add(str(groups))
    return sorted(group_names)

CORRELATION_STRIP_KEYS = frozenset({
    "rule_id",
    "insert_time",
    "modify_time",
    "created_by",
    "hits",
})

BIOC_STRIP_KEYS = frozenset({
    "rule_id",
    "number_of_issues",
    "source",
    "creation_time",
    "modification_time",
})

INDICATOR_STRIP_KEYS = frozenset({
    "rule_id",
    "id",
    "insert_time",
    "modify_time",
    "created_by",
    "modified_by",
    "modification_time",
    "creation_time",
})

CORTEX_IOC_INSERT_TEMPLATE: dict[str, Any] = {
    "severity": "SEV_020_LOW",
    "comment": "cptk-probe",
    "reputation": "BAD",
    "reliability": "C",
    "default_expiration_enabled": False,
    # Required even when default_expiration_enabled is false (epoch ms, UTC).
    "expiration_date": -1,
}


def _client(profile: CredentialProfile) -> TenantClient:
    return TenantClient(profile)


def assert_section_supported(section: AdminSection, platform: Platform) -> None:
    assert_operation_supported(OPERATION_BY_SECTION[section], platform)


def _list_paged_cortex_objects(
    profile: CredentialProfile,
    url: str,
    action: str,
    *,
    limit: int = 500,
    extended_view: bool = False,
) -> list[dict[str, Any]]:
    """List Cortex public API objects using search_from/search_to pages (max 100 per call)."""
    client = _client(profile)
    items: list[dict[str, Any]] = []
    search_from = 0
    while len(items) < limit:
        page_size = min(CORTEX_SEARCH_PAGE_SIZE, limit - len(items))
        search_to = search_from + page_size
        request_data: dict[str, Any] = {
            "search_from": search_from,
            "search_to": search_to,
        }
        if extended_view:
            request_data["extended_view"] = True
        data = client.post_json(
            url,
            action=action,
            payload=_request_data(request_data),
        )
        if not isinstance(data, dict):
            raise ValueError(f"Unexpected {action} response: {type(data)}")
        batch = [item for item in (data.get("objects") or []) if isinstance(item, dict)]
        items.extend(batch)
        if len(batch) < page_size:
            break
        search_from = search_to
    return items


def list_correlation_rules(profile: CredentialProfile, *, limit: int = 500) -> list[dict[str, Any]]:
    assert_section_supported("correlation-rules", profile.tenant_type)
    host = profile.host.rstrip("/")
    return _list_paged_cortex_objects(
        profile,
        correlations_get_url(host),
        "list correlation rules",
        limit=limit,
        extended_view=True,
    )


def get_correlation_rule(profile: CredentialProfile, name: str) -> Optional[dict[str, Any]]:
    assert_section_supported("correlation-rules", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    data = client.post_json(
        correlations_get_url(host),
        action=f"get correlation rule {name}",
        payload={
            "request_data": {
                "filters": [{"field": "name", "operator": "EQ", "value": name}],
                "extended_view": True,
            },
        },
    )
    if isinstance(data, dict):
        objects = data.get("objects") or []
        if objects and isinstance(objects[0], dict):
            return objects[0]
    return None


def insert_correlation_rules(profile: CredentialProfile, rules: list[dict[str, Any]]) -> tuple[Any, int]:
    assert_section_supported("correlation-rules", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    return client.post_json_with_status(
        correlations_insert_url(host),
        action="insert correlation rules",
        payload={"request_data": rules},
    )


def delete_correlation_rule(profile: CredentialProfile, name: str) -> tuple[Any, int]:
    assert_section_supported("correlation-rules", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    return client.post_json_with_status(
        correlations_delete_url(host),
        action=f"delete correlation rule {name}",
        payload={
            "request_data": {
                "filters": [{"field": "name", "operator": "EQ", "value": name}],
            },
        },
    )


def delete_correlation_rules(profile: CredentialProfile, names: list[str]) -> list[dict[str, Any]]:
    if not names:
        raise ValueError("names required")
    results: list[dict[str, Any]] = []
    for name in names:
        result, status = delete_correlation_rule(profile, name)
        results.append({"name": name, "status": status, "result": result})
    return results


def prepare_correlation_write(source: dict[str, Any], *, new_name: str) -> dict[str, Any]:
    doc = {key: value for key, value in source.items() if key not in CORRELATION_STRIP_KEYS}
    doc["name"] = new_name
    if "alert_name" in doc:
        doc["alert_name"] = new_name
    return doc


def list_biocs(profile: CredentialProfile, *, limit: int = 500) -> list[dict[str, Any]]:
    assert_section_supported("biocs", profile.tenant_type)
    host = profile.host.rstrip("/")
    return _list_paged_cortex_objects(
        profile,
        biocs_get_url(host),
        "list biocs",
        limit=limit,
        extended_view=True,
    )


def get_bioc(profile: CredentialProfile, name: str) -> Optional[dict[str, Any]]:
    assert_section_supported("biocs", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    data = client.post_json(
        biocs_get_url(host),
        action=f"get bioc {name}",
        payload={
            "request_data": {
                "filters": [{"field": "name", "operator": "EQ", "value": name}],
                "extended_view": True,
            },
        },
    )
    if isinstance(data, dict):
        objects = data.get("objects") or []
        if objects and isinstance(objects[0], dict):
            return objects[0]
    return None


def insert_biocs(profile: CredentialProfile, biocs: list[dict[str, Any]]) -> tuple[Any, int]:
    assert_section_supported("biocs", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    return client.post_json_with_status(
        biocs_insert_url(host),
        action="insert biocs",
        payload={"request_data": biocs},
    )


def delete_bioc(profile: CredentialProfile, name: str) -> tuple[Any, int]:
    assert_section_supported("biocs", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    return client.post_json_with_status(
        biocs_delete_url(host),
        action=f"delete bioc {name}",
        payload={
            "request_data": {
                "filters": [{"field": "name", "operator": "EQ", "value": name}],
            },
        },
    )


def delete_biocs(profile: CredentialProfile, names: list[str]) -> list[dict[str, Any]]:
    if not names:
        raise ValueError("names required")
    results: list[dict[str, Any]] = []
    for name in names:
        result, status = delete_bioc(profile, name)
        results.append({"name": name, "status": status, "result": result})
    return results


def prepare_bioc_write(source: dict[str, Any], *, new_name: str) -> dict[str, Any]:
    doc = {key: value for key, value in source.items() if key not in BIOC_STRIP_KEYS}
    doc["name"] = new_name
    return doc


def list_indicators(profile: CredentialProfile, *, limit: int = 100) -> list[dict[str, Any]]:
    assert_section_supported("indicators", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    platform = profile.tenant_type
    if platform in (Platform.XSOAR6, Platform.XSOAR8):
        data = client.post_json(
            xsoar_shaped_url(host, platform, "/indicators/search"),
            action="list indicators",
            payload={"query": "*", "size": limit, "from": 0},
        )
        if isinstance(data, dict):
            return [item for item in (data.get("iocObjects") or []) if isinstance(item, dict)]
        raise ValueError(f"Unexpected xsoar indicators response: {type(data)}")
    data = client.post_json(
        indicators_get_url(host),
        action="list indicators",
        payload={
            "request_data": {
                "search_from": 0,
                "search_to": limit,
            },
        },
    )
    if isinstance(data, dict):
        return [item for item in (data.get("objects") or data.get("indicators") or []) if isinstance(item, dict)]
    raise ValueError(f"Unexpected indicators response: {type(data)}")


def get_indicator(profile: CredentialProfile, indicator_id: str) -> Optional[dict[str, Any]]:
    assert_section_supported("indicators", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    platform = profile.tenant_type
    if platform in (Platform.XSOAR6, Platform.XSOAR8):
        data = client.post_json(
            xsoar_shaped_url(host, platform, "/indicators/search"),
            action=f"get indicator {indicator_id}",
            payload={"query": f'id:"{indicator_id}"', "size": 1},
        )
        if isinstance(data, dict):
            objects = data.get("iocObjects") or []
            if objects and isinstance(objects[0], dict):
                return objects[0]
        return None
    data = client.post_json(
        indicators_get_url(host),
        action=f"get indicator {indicator_id}",
        payload={
            "request_data": {
                "filters": [{"field": "rule_id", "operator": "IN", "value": [indicator_id]}],
            },
        },
    )
    if isinstance(data, dict):
        objects = data.get("objects") or data.get("indicators") or []
        if objects and isinstance(objects[0], dict):
            return objects[0]
    return None


def find_indicator_by_value(profile: CredentialProfile, value: str) -> Optional[dict[str, Any]]:
    assert_section_supported("indicators", profile.tenant_type)
    if not value:
        return None
    client = _client(profile)
    host = profile.host.rstrip("/")
    platform = profile.tenant_type
    if platform in (Platform.XSOAR6, Platform.XSOAR8):
        data = client.post_json(
            xsoar_shaped_url(host, platform, "/indicators/search"),
            action=f"find indicator value {value}",
            payload={"query": f'value:"{value}"', "size": 1},
        )
        if isinstance(data, dict):
            objects = data.get("iocObjects") or []
            if objects and isinstance(objects[0], dict):
                return objects[0]
        return None
    data = client.post_json(
        indicators_get_url(host),
        action=f"find indicator value {value}",
        payload={
            "request_data": {
                "filters": [{"field": "indicator", "operator": "EQ", "value": value}],
            },
        },
    )
    if isinstance(data, dict):
        objects = data.get("objects") or data.get("indicators") or []
        if objects and isinstance(objects[0], dict):
            return objects[0]
    return None


def prepare_cortex_indicator_write(source: dict[str, Any]) -> dict[str, Any]:
    doc = {key: value for key, value in source.items() if key not in INDICATOR_STRIP_KEYS}
    for key, value in CORTEX_IOC_INSERT_TEMPLATE.items():
        doc.setdefault(key, value)
    return doc


def create_xsoar_indicator(profile: CredentialProfile, source: dict[str, Any]) -> tuple[Any, int]:
    assert_section_supported("indicators", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    platform = profile.tenant_type
    if platform == Platform.XSOAR8:
        url = f"{host}/xsoar/public/v1/indicator/create"
    else:
        url = f"{host}/indicator/create"
    indicator_body = {
        "value": source.get("value") or source.get("indicator"),
        "indicator_type": source.get("indicator_type") or source.get("module") or "Domain",
        "score": source.get("score", 2),
        "source": source.get("source") or "cptk-copy",
    }
    return client.post_json_with_status(
        url,
        action="create xsoar indicator",
        payload={"indicator": indicator_body, "manually": True},
    )


def insert_indicators(profile: CredentialProfile, indicators: list[dict[str, Any]]) -> tuple[Any, int]:
    assert_section_supported("indicators", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    return client.post_json_with_status(
        indicators_insert_url(host),
        action="insert indicators",
        payload={"request_data": indicators},
    )


def xsoar_batch_delete_payload(indicator_ids: list[str]) -> dict[str, Any]:
    """Build batchDelete body for XSOAR 6/8 (ids-only returns HTTP 500 in lab)."""
    if not indicator_ids:
        raise ValueError("indicator_ids required")
    id_query = " or ".join(f'id:"{indicator_id}"' for indicator_id in indicator_ids)
    return {
        "ids": indicator_ids,
        "doNotWhitelist": True,
        "all": False,
        "filter": {
            "query": id_query,
            "size": max(len(indicator_ids), 5),
        },
    }


def delete_indicators(profile: CredentialProfile, ids: list[str]) -> tuple[Any, int]:
    assert_section_supported("indicators", profile.tenant_type)
    if not ids:
        raise ValueError("ids required")
    client = _client(profile)
    host = profile.host.rstrip("/")
    platform = profile.tenant_type
    if platform in (Platform.XSOAR6, Platform.XSOAR8):
        return client.post_json_with_status(
            indicators_batch_delete_url(host, platform),
            action="delete indicators",
            payload=xsoar_batch_delete_payload(ids),
        )
    return client.post_json_with_status(
        indicators_delete_url(host),
        action="delete indicators",
        payload={
            "request_data": {
                "filters": [
                    {"field": "rule_id", "operator": "IN", "value": ids},
                ],
            },
        },
    )


def list_rbac_users(profile: CredentialProfile) -> list[dict[str, Any]]:
    assert_section_supported("rbac-users", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    data = client.post_json(rbac_get_users_url(host), action="list rbac users", payload={})
    if isinstance(data, dict):
        reply = data.get("reply") or data.get("users") or []
        if isinstance(reply, list):
            return [item for item in reply if isinstance(item, dict)]
    raise ValueError(f"Unexpected rbac users response: {type(data)}")


def list_rbac_roles(profile: CredentialProfile, role_names: list[str]) -> list[dict[str, Any]]:
    assert_section_supported("rbac-roles", profile.tenant_type)
    if not role_names:
        return []
    client = _client(profile)
    host = profile.host.rstrip("/")
    roles: list[dict[str, Any]] = []
    for batch in _batch_names(role_names):
        data = client.post_json(
            rbac_get_roles_url(host),
            action="list rbac roles",
            payload=_request_data({"role_names": batch}),
        )
        if isinstance(data, dict):
            roles.extend(_flatten_rbac_reply(data))
        else:
            raise ValueError(f"Unexpected rbac roles response: {type(data)}")
    return roles


def list_rbac_groups(profile: CredentialProfile, group_names: list[str]) -> list[dict[str, Any]]:
    assert_section_supported("rbac-groups", profile.tenant_type)
    if not group_names:
        return []
    client = _client(profile)
    host = profile.host.rstrip("/")
    groups: list[dict[str, Any]] = []
    for batch in _batch_names(group_names):
        data = client.post_json(
            rbac_get_user_group_url(host),
            action="list rbac groups",
            payload=_request_data({"group_names": batch}),
        )
        if isinstance(data, dict):
            reply = data.get("reply") or data.get("groups") or []
            if isinstance(reply, list):
                groups.extend(item for item in reply if isinstance(item, dict))
            else:
                raise ValueError(f"Unexpected rbac groups response: {type(data)}")
        else:
            raise ValueError(f"Unexpected rbac groups response: {type(data)}")
    return groups


def set_user_role(profile: CredentialProfile, user_email: str, role_name: str) -> tuple[Any, int]:
    assert_section_supported("rbac-users", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    return client.post_json_with_status(
        rbac_set_user_role_url(host),
        action=f"set user role for {user_email}",
        payload=_request_data({"user_emails": [user_email], "role_name": role_name}),
    )


def list_api_keys(profile: CredentialProfile) -> list[dict[str, Any]]:
    assert_section_supported("api-keys", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    data = client.post_json(
        api_keys_get_url(host),
        action="list api keys",
        payload=_request_data({"filters": []}),
    )
    if isinstance(data, dict):
        reply = data.get("reply")
        if isinstance(reply, dict):
            rows = reply.get("DATA") or reply.get("data") or []
            if isinstance(rows, list):
                return [item for item in rows if isinstance(item, dict)]
        if isinstance(reply, list):
            return [item for item in reply if isinstance(item, dict)]
    raise ValueError(f"Unexpected api keys response: {type(data)}")


def generate_api_key(
    profile: CredentialProfile,
    comment: str,
    *,
    roles: list[str],
    security_level: str = "standard",
    expiration: Optional[int] = None,
) -> tuple[Any, int]:
    assert_section_supported("api-keys", profile.tenant_type)
    if not roles:
        raise ValueError("roles required (at least one role name)")
    if security_level not in ("standard", "advanced"):
        raise ValueError("security_level must be standard or advanced")
    client = _client(profile)
    host = profile.host.rstrip("/")
    request_payload: dict[str, Any] = {
        "roles": roles,
        "security_level": security_level,
        "comment": comment or "cortex-ps-toolkit",
    }
    if expiration is not None:
        request_payload["expiration"] = expiration
    return client.post_json_with_status(
        api_keys_generate_url(host),
        action="generate api key",
        payload=_request_data(request_payload),
    )


def delete_api_key(profile: CredentialProfile, key_id: str) -> tuple[Any, int]:
    assert_section_supported("api-keys", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    key_value: int | str = int(key_id) if str(key_id).isdigit() else key_id
    return client.post_json_with_status(
        api_keys_delete_url(host),
        action=f"delete api key {key_id}",
        payload=_request_data({
            "filters": [{"field": "id", "operator": "in", "value": [key_value]}],
        }),
    )


def fetch_section_items(profile: CredentialProfile, section: AdminSection) -> list[dict[str, Any]]:
    if section == "correlation-rules":
        return list_correlation_rules(profile)
    if section == "biocs":
        return list_biocs(profile)
    if section == "indicators":
        return list_indicators(profile)
    if section == "rbac-users":
        return list_rbac_users(profile)
    if section == "rbac-roles":
        users = list_rbac_users(profile)
        return list_rbac_roles(profile, _distinct_user_role_names(users))
    if section == "rbac-groups":
        users = list_rbac_users(profile)
        return list_rbac_groups(profile, _distinct_user_group_names(users))
    if section == "api-keys":
        return list_api_keys(profile)
    if section not in ADMIN_SECTIONS:
        raise ValueError(f"Unknown section: {section}")
    raise ValueError(f"No fetch handler for section: {section}")
