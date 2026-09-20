from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from cortex_ps_toolkit.cache.refresh import (
    reset_cache_refresh_locks,
    run_cache_refresh,
    should_skip_elective_refresh,
)
from cortex_ps_toolkit.credentials import create_profile_from_input
from cortex_ps_toolkit.playbooks.cache import write_playbooks_cache
from cortex_ps_toolkit.runtime.graph import RefreshMode


@pytest.fixture(autouse=True)
def _reset_locks() -> None:
    reset_cache_refresh_locks()


def test_elective_refresh_skips_when_ttl_fresh(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "credentials.json"
    monkeypatch.setattr("cortex_ps_toolkit.credentials.credentials_collection_path", lambda: dest)
    monkeypatch.setenv("CORTEX_PS_DATA_DIR", str(tmp_path / "data"))

    profile = create_profile_from_input({
        "label": "TTL Profile",
        "slug": "ttl-profile",
        "url": "https://tenant.example.test",
        "key": "secret",
        "tenant_type": "xsoar8",
        "api_id": "1",
        "cache_ttl_seconds": 600,
    })
    write_playbooks_cache(profile, [{"id": "pb1", "name": "Main"}])

    with patch("cortex_ps_toolkit.playbooks.service.refresh_playbooks_cache") as mock_refresh:
        from cortex_ps_toolkit.playbooks.cache import load_playbooks_index
        from cortex_ps_toolkit.playbooks.service import refresh_playbooks_cache

        result = run_cache_refresh(
            profile,
            "playbooks",
            load_index=load_playbooks_index,
            refresh=refresh_playbooks_cache,
            mode=RefreshMode.ELECTIVE,
        )

    assert result["cache_action"] == "used_cache"
    mock_refresh.assert_not_called()


def test_required_refresh_always_fetches(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "credentials.json"
    monkeypatch.setattr("cortex_ps_toolkit.credentials.credentials_collection_path", lambda: dest)
    monkeypatch.setenv("CORTEX_PS_DATA_DIR", str(tmp_path / "data"))

    profile = create_profile_from_input({
        "label": "Required",
        "slug": "required-profile",
        "url": "https://tenant.example.test",
        "key": "secret",
        "tenant_type": "xsoar8",
        "api_id": "1",
    })
    write_playbooks_cache(profile, [{"id": "pb1", "name": "Main"}])

    with patch("cortex_ps_toolkit.playbooks.service.refresh_playbooks_cache") as mock_refresh:
        mock_refresh.return_value = {"profile": profile.slug, "count": 1}
        from cortex_ps_toolkit.playbooks.cache import load_playbooks_index
        from cortex_ps_toolkit.playbooks.service import refresh_playbooks_cache

        result = run_cache_refresh(
            profile,
            "playbooks",
            load_index=load_playbooks_index,
            refresh=refresh_playbooks_cache,
            mode=RefreshMode.REQUIRED,
        )

    assert result["cache_action"] == "refreshed"
    mock_refresh.assert_called_once()


def test_cache_refresh_lock_serializes_concurrent_refreshes(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    dest = tmp_path / "credentials.json"
    monkeypatch.setattr("cortex_ps_toolkit.credentials.credentials_collection_path", lambda: dest)
    monkeypatch.setenv("CORTEX_PS_DATA_DIR", str(tmp_path / "data"))

    profile = create_profile_from_input({
        "label": "Lock",
        "slug": "lock-profile",
        "url": "https://tenant.example.test",
        "key": "secret",
        "tenant_type": "xsoar8",
        "api_id": "1",
    })

    inner_lock = threading.Lock()
    concurrent = 0
    max_concurrent = 0

    def refresh(_profile):
        nonlocal concurrent, max_concurrent
        with inner_lock:
            concurrent += 1
            max_concurrent = max(max_concurrent, concurrent)
        time.sleep(0.05)
        with inner_lock:
            concurrent -= 1
        return {"profile": profile.slug, "count": 0}

    from cortex_ps_toolkit.playbooks.cache import load_playbooks_index

    def worker() -> None:
        run_cache_refresh(
            profile,
            "playbooks",
            load_index=load_playbooks_index,
            refresh=refresh,
            mode=RefreshMode.REQUIRED,
        )

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert max_concurrent == 1


def test_should_skip_elective_respects_profile_ttl() -> None:
    from cortex_ps_toolkit.credentials import CredentialProfile
    from cortex_ps_toolkit.platforms import Platform

    fresh = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    profile = CredentialProfile(
        id="1",
        label="x",
        slug="x",
        url="https://example.test",
        api_id="1",
        key="k",
        tenant_type=Platform.XSOAR8,
        cache_ttl_seconds=600,
    )
    assert should_skip_elective_refresh(profile, refreshed_at=fresh, mode=RefreshMode.ELECTIVE) is True
    assert should_skip_elective_refresh(profile, refreshed_at=fresh, mode=RefreshMode.REQUIRED) is False

    old = (datetime.now(timezone.utc) - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert should_skip_elective_refresh(profile, refreshed_at=old, mode=RefreshMode.ELECTIVE) is False
