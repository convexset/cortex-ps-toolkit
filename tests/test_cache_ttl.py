from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from cortex_ps_toolkit.cache.ensure import ensure_playbooks_cache
from cortex_ps_toolkit.cache.ttl import cache_age_seconds, is_cache_stale
from cortex_ps_toolkit.playbooks.cache import write_playbooks_cache
from cortex_ps_toolkit.settings import save_settings


def test_is_cache_stale_respects_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORTEX_PS_CACHE_TTL_SEC", "300")
    fresh = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert is_cache_stale(fresh) is False
    assert is_cache_stale(old) is True


def test_cache_age_seconds_parses_utc_stamp() -> None:
    stamp = "2026-09-17T10:00:00Z"
    assert cache_age_seconds(stamp) is not None
    assert cache_age_seconds(stamp) >= 0


from unittest.mock import patch


@patch("cortex_ps_toolkit.playbooks.service.refresh_playbooks_cache")
def test_ensure_playbooks_cache_skips_when_fresh(
    mock_refresh,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cortex_ps_toolkit.credentials import CredentialProfile, create_profile_from_input

    dest = tmp_path / "credentials.json"
    monkeypatch.setattr("cortex_ps_toolkit.credentials.credentials_collection_path", lambda: dest)
    monkeypatch.setenv("CORTEX_PS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CORTEX_PS_CACHE_TTL_SEC", "300")

    profile = create_profile_from_input({
        "label": "Cache TTL",
        "slug": "cache-ttl-test",
        "url": "https://tenant.example.test",
        "key": "secret",
        "tenant_type": "xsoar8",
        "api_id": "1",
    })
    write_playbooks_cache(profile, [{"id": "pb1", "name": "Main"}])

    result = ensure_playbooks_cache(profile)
    assert result["cache_action"] == "used_cache"
    mock_refresh.assert_not_called()
