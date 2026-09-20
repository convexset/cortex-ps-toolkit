"""Tenant HTTP for design-time content assets."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..core.client import TenantClient
from ..core.paths import (
    classifier_search_url,
    content_bundle_export_url,
    incidentfield_delete_url,
    incidentfield_write_url,
    incidentfields_list_url,
    incidenttype_delete_url,
    incidenttype_list_url,
    incidenttype_write_url,
    layout_delete_url,
    layout_get_url,
    layouts_list_url,
    preprocess_rules_list_url,
    xsoar_webapp_url,
)
from ..credentials import CredentialProfile
from ..platforms import Platform, assert_operation_supported
from .types import ASSET_KINDS, OPERATION_BY_ASSET, AssetKind


def _client(profile: CredentialProfile) -> TenantClient:
    return TenantClient(profile)


def assert_asset_supported(asset: AssetKind, platform: Platform) -> None:
    assert_operation_supported(OPERATION_BY_ASSET[asset], platform)


def fetch_layouts(profile: CredentialProfile) -> list[dict[str, Any]]:
    assert_asset_supported("layouts", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    data = client.get_json(layouts_list_url(host, profile.tenant_type), action="list layouts")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    raise ValueError(f"Unexpected layouts response: {type(data)}")


def fetch_layout(profile: CredentialProfile, layout_id: str) -> dict[str, Any]:
    assert_asset_supported("layouts", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    data = client.get_json(
        layout_get_url(host, profile.tenant_type, layout_id),
        action=f"get layout {layout_id}",
    )
    if isinstance(data, dict):
        return data
    raise ValueError(f"Unexpected layout response: {type(data)}")


def fetch_classifiers(profile: CredentialProfile) -> list[dict[str, Any]]:
    assert_asset_supported("classifiers", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    data = client.post_json(
        classifier_search_url(host, profile.tenant_type),
        action="search classifiers",
        payload={},
    )
    if isinstance(data, dict):
        items = data.get("classifiers") or []
        return [item for item in items if isinstance(item, dict)]
    raise ValueError(f"Unexpected classifiers response: {type(data)}")


def fetch_preprocess_rules(profile: CredentialProfile) -> list[dict[str, Any]]:
    assert_asset_supported("preprocess", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    data = client.get_json(
        preprocess_rules_list_url(host, profile.tenant_type),
        action="list preprocess rules",
    )
    if data is None:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    raise ValueError(f"Unexpected preprocess response: {type(data)}")


def fetch_incident_fields(profile: CredentialProfile) -> list[dict[str, Any]]:
    assert_asset_supported("incident-fields", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    data = client.get_json(
        incidentfields_list_url(host, profile.tenant_type),
        action="list incident fields",
    )
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    raise ValueError(f"Unexpected incident fields response: {type(data)}")


def fetch_incident_types(profile: CredentialProfile) -> list[dict[str, Any]]:
    assert_asset_supported("incident-types", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    data = client.get_json(
        incidenttype_list_url(host, profile.tenant_type),
        action="list incident types",
    )
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    raise ValueError(f"Unexpected incident types response: {type(data)}")


def write_incident_field(profile: CredentialProfile, document: dict[str, Any]) -> tuple[Any, int]:
    assert_asset_supported("incident-fields", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    return client.post_json_with_status(
        incidentfield_write_url(host, profile.tenant_type),
        action=f"write incident field {document.get('id')}",
        payload=document,
    )


def write_incident_type(profile: CredentialProfile, document: dict[str, Any]) -> tuple[Any, int]:
    assert_asset_supported("incident-types", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    return client.post_json_with_status(
        incidenttype_write_url(host, profile.tenant_type),
        action=f"write incident type {document.get('id')}",
        payload=document,
    )


def delete_incident_field(profile: CredentialProfile, field_id: str) -> tuple[Any, int]:
    assert_asset_supported("incident-fields", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    url = incidentfield_delete_url(host, profile.tenant_type, field_id)
    response = client.session.delete(url, timeout=client.timeout)
    client._raise_for_status(response, f"delete incident field {field_id}")
    return client._response_json(response), response.status_code


def delete_incident_type(profile: CredentialProfile, type_id: str) -> tuple[Any, int]:
    assert_asset_supported("incident-types", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    return client.post_json_with_status(
        incidenttype_delete_url(host, profile.tenant_type),
        action=f"delete incident type {type_id}",
        payload={"id": type_id},
    )


def fetch_asset_items(profile: CredentialProfile, asset: AssetKind) -> list[dict[str, Any]]:
    if asset == "layouts":
        return fetch_layouts(profile)
    if asset == "classifiers":
        return fetch_classifiers(profile)
    if asset == "preprocess":
        return fetch_preprocess_rules(profile)
    if asset == "incident-fields":
        return fetch_incident_fields(profile)
    if asset == "incident-types":
        return fetch_incident_types(profile)
    raise ValueError(f"Unknown asset: {asset}")


def export_bundle_bytes(profile: CredentialProfile) -> bytes:
    if profile.tenant_type != Platform.XSOAR6:
        raise UnsupportedBundleExport(f"Bundle export is only supported on xsoar6, not {profile.tenant_type.value}")
    client = _client(profile)
    url = content_bundle_export_url(profile.host.rstrip("/"), profile.tenant_type)
    return client.get_bytes(url, action="export content bundle", timeout=300.0)


def delete_layout(profile: CredentialProfile, layout_id: str) -> tuple[Any, int]:
    assert_asset_supported("layouts", profile.tenant_type)
    client = _client(profile)
    host = profile.host.rstrip("/")
    encoded = quote(layout_id, safe="")
    if profile.tenant_type == Platform.XSOAR6:
        url = f"{host}/layout/{encoded}/remove"
    else:
        url = layout_delete_url(host, profile.tenant_type, layout_id)
    response = client.session.post(url, json={}, timeout=client.timeout)
    client._raise_for_status(response, f"delete layout {layout_id}")
    return client._response_json(response), response.status_code


def delete_classifier(profile: CredentialProfile, classifier_id: str) -> tuple[Any, int]:
    assert_asset_supported("classifiers", profile.tenant_type)
    if profile.tenant_type not in (Platform.XSOAR6, Platform.XSOAR8):
        raise UnsupportedDelete(f"Classifier delete not supported on {profile.tenant_type.value}")
    client = _client(profile)
    host = profile.host.rstrip("/")
    encoded = quote(classifier_id, safe="")
    if profile.tenant_type == Platform.XSOAR6:
        url = f"{host}/classifier/{encoded}"
    else:
        url = xsoar_webapp_url(host, profile.tenant_type, f"/classifier/{encoded}")
    response = client.session.delete(url, timeout=client.timeout)
    client._raise_for_status(response, f"delete classifier {classifier_id}")
    return client._response_json(response), response.status_code


def delete_preprocess_rule(profile: CredentialProfile, rule_id: str) -> tuple[Any, int]:
    assert_asset_supported("preprocess", profile.tenant_type)
    if profile.tenant_type not in (Platform.XSOAR6, Platform.XSOAR8):
        raise UnsupportedDelete(f"Preprocess delete not supported on {profile.tenant_type.value}")
    client = _client(profile)
    host = profile.host.rstrip("/")
    encoded = quote(rule_id, safe="")
    if profile.tenant_type == Platform.XSOAR6:
        url = f"{host}/preprocess/rule/{encoded}"
    else:
        url = xsoar_webapp_url(host, profile.tenant_type, f"/preProcessRule/{encoded}")
    response = client.session.delete(url, timeout=client.timeout)
    client._raise_for_status(response, f"delete preprocess rule {rule_id}")
    return client._response_json(response), response.status_code


class UnsupportedBundleExport(RuntimeError):
    """Bundle export unavailable on this platform."""


class UnsupportedDelete(RuntimeError):
    """Delete unavailable for this asset/platform combination."""
