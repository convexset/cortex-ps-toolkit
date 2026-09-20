from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cortex_ps_toolkit.credentials import (
    CredentialProfile,
    is_expired,
    parse_expiry,
    purge_expired_profiles,
    set_profile_expiry,
    set_profile_verify_ssl,
    upsert_profile,
)
from cortex_ps_toolkit.platforms import Platform


def test_parse_expiry_end_month() -> None:
    assert parse_expiry("end Nov 2026") == "2026-11-30T23:59:59Z"


def test_parse_expiry_iso_date() -> None:
    assert parse_expiry("2026-11-30") == "2026-11-30T23:59:59Z"


def test_is_expired() -> None:
    profile = CredentialProfile(
        id="1",
        label="test",
        slug="test",
        url="https://example.test",
        api_id="1",
        key="secret",
        tenant_type=Platform.XSOAR8,
        expires_at="2020-01-01T23:59:59Z",
    )
    now = datetime(2021, 1, 1, tzinfo=timezone.utc)
    assert is_expired(profile, now=now)


def test_purge_expired_profiles(tmp_path: Path) -> None:
    dest = tmp_path / "credentials.json"
    expired = CredentialProfile(
        id="exp",
        label="expired",
        slug="expired",
        url="https://example.test",
        api_id="1",
        key="secret",
        tenant_type=Platform.XSOAR8,
        expires_at="2020-01-01T23:59:59Z",
    )
    active = CredentialProfile(
        id="act",
        label="active",
        slug="active",
        url="https://example.test",
        api_id="2",
        key="secret2",
        tenant_type=Platform.XSOAR8,
    )
    upsert_profile(expired, dest)
    upsert_profile(active, dest)
    removed = purge_expired_profiles(dest)
    assert [item.slug for item in removed] == ["expired"]
    payload = json.loads(dest.read_text(encoding="utf-8"))
    assert len(payload["profiles"]) == 1
    assert payload["profiles"][0]["slug"] == "active"


def test_set_profile_verify_ssl(tmp_path: Path) -> None:
    dest = tmp_path / "credentials.json"
    profile = CredentialProfile(
        id="1",
        label="lab",
        slug="lab",
        url="https://example.test",
        api_id="1",
        key="secret",
        tenant_type=Platform.XSOAR6,
    )
    upsert_profile(profile, dest)
    updated = set_profile_verify_ssl("lab", False, dest)
    assert updated.verify_ssl is False


def test_set_profile_expiry(tmp_path: Path) -> None:
    dest = tmp_path / "credentials.json"
    profile = CredentialProfile(
        id="1",
        label="lab",
        slug="lab",
        url="https://example.test",
        api_id="1",
        key="secret",
        tenant_type=Platform.XSOAR8,
    )
    upsert_profile(profile, dest)
    updated = set_profile_expiry("lab", "end Nov 2026", dest)
    assert updated.expires_at == "2026-11-30T23:59:59Z"
    cleared = set_profile_expiry("lab", None, dest)
    assert cleared.expires_at == ""
