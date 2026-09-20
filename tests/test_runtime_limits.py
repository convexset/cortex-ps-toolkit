from __future__ import annotations

import threading
import time

import pytest

from cortex_ps_toolkit.credentials import CredentialProfile
from cortex_ps_toolkit.platforms import Platform
from cortex_ps_toolkit.runtime.limits import LimitRegistry, reset_limit_registry, resolve_concurrency_limits


@pytest.fixture(autouse=True)
def _reset_limits() -> None:
    reset_limit_registry()


def _profile(**overrides) -> CredentialProfile:
    base = {
        "id": "1",
        "label": "Lab",
        "slug": "lab",
        "url": "https://tenant-a.example.test",
        "api_id": "1",
        "key": "secret",
        "tenant_type": Platform.XSOAR8,
    }
    base.update(overrides)
    return CredentialProfile(**base)


def test_resolve_concurrency_limits_uses_profile_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORTEX_PS_MAX_INFLIGHT_PER_HOST", "5")
    monkeypatch.setenv("CORTEX_PS_MAX_INFLIGHT_GLOBAL", "20")
    profile = _profile(max_inflight_per_host=2, max_inflight_global=7)
    limits = resolve_concurrency_limits(profile)
    assert limits.per_host == 2
    assert limits.global_max == 7


def test_limit_registry_enforces_global_cap() -> None:
    registry = LimitRegistry()
    profile = _profile(max_inflight_global=2)

    active_holders = 0
    count_lock = threading.Lock()
    both_holding = threading.Event()
    release = threading.Event()

    def hold() -> None:
        nonlocal active_holders
        with registry.acquire(host_key=None, profile=profile):
            with count_lock:
                active_holders += 1
                if active_holders == 2:
                    both_holding.set()
            release.wait(timeout=2)

    first = threading.Thread(target=hold)
    second = threading.Thread(target=hold)
    first.start()
    second.start()
    assert both_holding.wait(timeout=1)

    blocked = threading.Event()

    def try_acquire() -> None:
        with registry.acquire(host_key=None, profile=profile):
            blocked.set()

    third = threading.Thread(target=try_acquire)
    third.start()
    time.sleep(0.05)
    assert not blocked.is_set()

    release.set()
    first.join(timeout=2)
    second.join(timeout=2)
    assert blocked.wait(timeout=1)
    third.join(timeout=2)


def test_same_host_shares_per_host_semaphore() -> None:
    registry = LimitRegistry()
    host = "https://shared-host.example.test"
    profile_a = _profile(slug="a", url=f"{host}/a", api_id="1", max_inflight_per_host=1)
    profile_b = _profile(slug="b", url=f"{host}/b", api_id="2", max_inflight_per_host=1)

    holder_ready = threading.Event()
    release = threading.Event()

    def hold(profile: CredentialProfile) -> None:
        with registry.acquire(host_key=host, profile=profile):
            holder_ready.set()
            release.wait(timeout=2)

    first = threading.Thread(target=hold, args=(profile_a,))
    first.start()
    assert holder_ready.wait(timeout=1)

    second_ready = threading.Event()

    def try_second() -> None:
        with registry.acquire(host_key=host, profile=profile_b):
            second_ready.set()

    second = threading.Thread(target=try_second)
    second.start()
    time.sleep(0.05)
    assert not second_ready.is_set()

    release.set()
    first.join(timeout=2)
    assert second_ready.wait(timeout=1)
    second.join(timeout=2)
