"""Per-host and global concurrency limits for tenant API operations."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional

from ..credentials import CredentialProfile
from ..settings import (
    default_max_inflight_global,
    default_max_inflight_per_host,
    max_inflight_global,
    max_inflight_per_host,
)


@dataclass(frozen=True)
class ConcurrencyLimits:
    per_host: int
    global_max: int


def resolve_concurrency_limits(profile: Optional[CredentialProfile] = None) -> ConcurrencyLimits:
    host_limit = default_max_inflight_per_host()
    global_limit = default_max_inflight_global()
    if profile is not None:
        if profile.max_inflight_per_host is not None:
            host_limit = profile.max_inflight_per_host
        if profile.max_inflight_global is not None:
            global_limit = profile.max_inflight_global
    return ConcurrencyLimits(
        per_host=max(1, int(host_limit)),
        global_max=max(1, int(global_limit)),
    )


class _HostSemaphore:
    def __init__(self, limit: int):
        self.limit = limit
        self._semaphore = threading.BoundedSemaphore(limit)


class LimitRegistry:
    """Shared in-flight caps: per API host and global across all hosts."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._host_semaphores: dict[str, _HostSemaphore] = {}
        self._global_semaphore: Optional[threading.BoundedSemaphore] = None
        self._global_limit: int = 0

    def _host_semaphore(self, host_key: str, limit: int) -> _HostSemaphore:
        with self._lock:
            existing = self._host_semaphores.get(host_key)
            if existing is None:
                existing = _HostSemaphore(limit)
                self._host_semaphores[host_key] = existing
            elif limit < existing.limit:
                # Keep the stricter limit already in effect for this host.
                pass
            return self._host_semaphores[host_key]

    def _global(self, limit: int) -> threading.BoundedSemaphore:
        with self._lock:
            if self._global_semaphore is None or limit != self._global_limit:
                self._global_semaphore = threading.BoundedSemaphore(limit)
                self._global_limit = limit
            return self._global_semaphore

    @contextmanager
    def acquire(
        self,
        *,
        host_key: Optional[str] = None,
        profile: Optional[CredentialProfile] = None,
    ) -> Iterator[None]:
        limits = resolve_concurrency_limits(profile)
        global_sem = self._global(limits.global_max)
        global_sem.acquire()
        host_sem: Optional[_HostSemaphore] = None
        try:
            if host_key:
                host_sem = self._host_semaphore(host_key, limits.per_host)
                host_sem._semaphore.acquire()
            yield
        finally:
            if host_sem is not None:
                host_sem._semaphore.release()
            global_sem.release()


_default_registry = LimitRegistry()


def get_limit_registry() -> LimitRegistry:
    return _default_registry


def reset_limit_registry() -> None:
    global _default_registry
    _default_registry = LimitRegistry()


def profile_host_key(profile: CredentialProfile) -> str:
    return profile.host
