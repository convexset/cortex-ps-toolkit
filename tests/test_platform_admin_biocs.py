"""Tests for platform admin BIOC APIs."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cortex_ps_toolkit.credentials import CredentialProfile
from cortex_ps_toolkit.platform_admin.api import (
    delete_bioc,
    delete_biocs,
    get_bioc,
    insert_biocs,
    list_biocs,
    prepare_bioc_write,
)
from cortex_ps_toolkit.platforms import Platform, UnsupportedOperation


def _profile(platform: Platform = Platform.XSIAM) -> CredentialProfile:
    return CredentialProfile(
        id="test-id",
        label="biocs",
        slug="biocs-xsiam",
        url="https://tenant.example.test",
        api_id="42",
        key="secret-key",
        tenant_type=platform,
        verify_ssl=True,
    )


def test_prepare_bioc_write_strips_rule_id() -> None:
    source = {
        "name": "Original BIOC",
        "rule_id": 99,
        "type": "EXECUTION",
        "severity": "SEV_030_MEDIUM",
        "status": "enabled",
        "is_xql": False,
    }
    doc = prepare_bioc_write(source, new_name="Copied BIOC")
    assert doc["name"] == "Copied BIOC"
    assert "rule_id" not in doc
    assert doc["type"] == "EXECUTION"


@pytest.mark.parametrize("platform", [Platform.XSIAM, Platform.XDR5])
def test_list_biocs_uses_get_endpoint(platform: Platform) -> None:
    profile = _profile(platform)
    with patch("cortex_ps_toolkit.platform_admin.api.TenantClient") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        client.post_json.return_value = {
            "objects_count": 1,
            "objects": [{"rule_id": 1, "name": "Test BIOC", "type": "EXECUTION"}],
        }
        items = list_biocs(profile)
    assert len(items) == 1
    assert items[0]["name"] == "Test BIOC"
    call = client.post_json.call_args
    assert call.args[0].endswith("/public_api/v1/bioc/get")
    assert call.kwargs["payload"]["request_data"]["extended_view"] is True


def test_get_bioc_filters_by_name() -> None:
    profile = _profile()
    with patch("cortex_ps_toolkit.platform_admin.api.TenantClient") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        client.post_json.return_value = {"objects": [{"name": "Probe BIOC"}]}
        item = get_bioc(profile, "Probe BIOC")
    assert item is not None
    assert item["name"] == "Probe BIOC"
    filters = client.post_json.call_args.kwargs["payload"]["request_data"]["filters"]
    assert filters == [{"field": "name", "operator": "EQ", "value": "Probe BIOC"}]


def test_insert_biocs_posts_request_data_array() -> None:
    profile = _profile()
    bioc = {"name": "New BIOC", "type": "EXECUTION", "severity": "SEV_020_LOW", "status": "enabled"}
    with patch("cortex_ps_toolkit.platform_admin.api.TenantClient") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        client.post_json_with_status.return_value = ({"added_objects": [{"id": 1}]}, 200)
        result, status = insert_biocs(profile, [bioc])
    assert status == 200
    call = client.post_json_with_status.call_args
    assert call.args[0].endswith("/public_api/v1/bioc/insert")
    assert call.kwargs["payload"] == {"request_data": [bioc]}


def test_delete_bioc_filters_by_name() -> None:
    profile = _profile()
    with patch("cortex_ps_toolkit.platform_admin.api.TenantClient") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        client.post_json_with_status.return_value = ({"objects_count": 1, "objects": [1]}, 200)
        result, status = delete_bioc(profile, "Old BIOC")
    assert status == 200
    call = client.post_json_with_status.call_args
    assert call.args[0].endswith("/public_api/v1/bioc/delete")
    filters = call.kwargs["payload"]["request_data"]["filters"]
    assert filters == [{"field": "name", "operator": "EQ", "value": "Old BIOC"}]


def test_delete_biocs_loops_names() -> None:
    profile = _profile()
    with patch("cortex_ps_toolkit.platform_admin.api.delete_bioc") as mock_delete:
        mock_delete.side_effect = [
            ({"objects_count": 1}, 200),
            ({"objects_count": 1}, 200),
        ]
        results = delete_biocs(profile, ["A", "B"])
    assert len(results) == 2
    assert mock_delete.call_count == 2


def test_list_biocs_unsupported_on_xsoar6() -> None:
    profile = _profile(Platform.XSOAR6)
    with pytest.raises(UnsupportedOperation):
        list_biocs(profile)
