"""Tests for RBAC and API key request payloads."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.credentials import CredentialProfile
from cortex_ps_toolkit.platform_admin.api import (
    _distinct_user_group_names,
    _distinct_user_role_names,
    delete_api_key,
    fetch_section_items,
    generate_api_key,
    list_api_keys,
    list_rbac_groups,
    list_rbac_roles,
)
from cortex_ps_toolkit.platform_admin.cache import write_cache
from cortex_ps_toolkit.platforms import Platform


def _profile() -> CredentialProfile:
    return CredentialProfile(
        id="id-1",
        label="Lab",
        slug="lab-xsiam",
        url="https://tenant.example.test",
        api_id="1",
        key="secret",
        tenant_type=Platform.XSIAM,
        verify_ssl=True,
    )


def test_distinct_user_role_and_group_names() -> None:
    users = [
        {"user_email": "a@example.test", "role_name": "Investigator", "groups": ["SOC"]},
        {"user_email": "b@example.test", "role": "Admin", "groups": ["SOC", "IR"]},
    ]
    assert _distinct_user_role_names(users) == ["Admin", "Investigator"]
    assert _distinct_user_group_names(users) == ["IR", "SOC"]


@patch("cortex_ps_toolkit.platform_admin.api.TenantClient")
def test_list_rbac_roles_wraps_request_data(mock_cls: MagicMock) -> None:
    client = MagicMock()
    mock_cls.return_value = client
    client.post_json.return_value = {"reply": [[{"pretty_name": "Investigator"}]]}

    roles = list_rbac_roles(_profile(), ["Investigator", "Admin"])

    assert len(roles) == 1
    assert client.post_json.call_args.kwargs["payload"] == {
        "request_data": {"role_names": ["Investigator", "Admin"]},
    }


@patch("cortex_ps_toolkit.platform_admin.api.list_rbac_users")
@patch("cortex_ps_toolkit.platform_admin.api.list_rbac_groups")
def test_fetch_rbac_groups_collects_names_from_users(mock_groups, mock_users) -> None:
    mock_users.return_value = [{"groups": ["SOC Users Group"]}]
    mock_groups.return_value = [{"group_name": "SOC Users Group"}]

    items = fetch_section_items(_profile(), "rbac-groups")

    assert items == [{"group_name": "SOC Users Group"}]
    mock_groups.assert_called_once_with(_profile(), ["SOC Users Group"])


@patch("cortex_ps_toolkit.platform_admin.api.TenantClient")
def test_list_api_keys_parses_reply_data(mock_cls: MagicMock) -> None:
    client = MagicMock()
    mock_cls.return_value = client
    client.post_json.return_value = {"reply": {"DATA": [{"id": 933, "comment": "automation"}]}}

    keys = list_api_keys(_profile())

    assert keys[0]["id"] == 933
    assert client.post_json.call_args.kwargs["payload"] == {"request_data": {"filters": []}}


def test_generate_api_key_requires_roles() -> None:
    import pytest

    with pytest.raises(ValueError, match="roles required"):
        generate_api_key(_profile(), "automation", roles=[])


@patch("cortex_ps_toolkit.platform_admin.api.TenantClient")
def test_generate_api_key_wraps_request_data(mock_cls: MagicMock) -> None:
    client = MagicMock()
    mock_cls.return_value = client
    client.post_json_with_status.return_value = ({"reply": {"key": "secret-once"}}, 200)

    result, status = generate_api_key(
        _profile(),
        "automation key",
        roles=["Investigator"],
        security_level="advanced",
        expiration=1789902721000,
    )

    assert status == 200
    assert result["reply"]["key"] == "secret-once"
    assert client.post_json_with_status.call_args.kwargs["payload"] == {
        "request_data": {
            "roles": ["Investigator"],
            "security_level": "advanced",
            "comment": "automation key",
            "expiration": 1789902721000,
        },
    }


@patch("cortex_ps_toolkit.platform_admin.api.TenantClient")
def test_delete_api_key_wraps_request_data(mock_cls: MagicMock) -> None:
    client = MagicMock()
    mock_cls.return_value = client
    client.post_json_with_status.return_value = ({}, 200)

    delete_api_key(_profile(), "933")

    assert client.post_json_with_status.call_args.kwargs["payload"] == {
        "request_data": {"filters": [{"field": "id", "operator": "in", "value": [933]}]},
    }


def test_write_cache_api_keys_preserve_expiration() -> None:
    profile = _profile()
    path = write_cache(profile, "api-keys", [{
        "id": 933,
        "comment": "automation",
        "roles": ["Investigator"],
        "created_by": "user@example.test",
        "creation_time": 1700000000000,
        "expiration": 1789902721000,
        "security_level": "standard",
    }])
    payload = json.loads(path.read_text(encoding="utf-8"))
    item = payload["items"][0]
    assert item["expiration"] == 1789902721000
    assert item["creation_time"] == 1700000000000
    assert item["created_by"] == "user@example.test"
    assert item["security_level"] == "standard"


def test_write_cache_rbac_users_use_email() -> None:
    profile = _profile()
    path = write_cache(profile, "rbac-users", [{
        "user_email": "user@example.test",
        "user_first_name": "Pat",
        "user_last_name": "Lee",
        "role_name": "Investigator",
        "user_type": "sso",
    }])
    payload = path.read_text(encoding="utf-8")
    assert "user@example.test" in payload
    assert "Pat Lee" in payload
