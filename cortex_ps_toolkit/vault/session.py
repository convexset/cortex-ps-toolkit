"""In-process vault unlock session (passphrase never persisted)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

DEFAULT_IDLE_SECONDS = 15 * 60


@dataclass
class VaultSession:
    vmk: bytes
    unlocked_at: datetime
    expires_at: datetime


_session: Optional[VaultSession] = None
_idle_seconds = DEFAULT_IDLE_SECONDS


def configure_idle_timeout(seconds: int) -> None:
    global _idle_seconds
    _idle_seconds = max(60, int(seconds))


def unlock_session(vmk: bytes) -> VaultSession:
    global _session
    now = datetime.now(timezone.utc)
    _session = VaultSession(
        vmk=bytes(vmk),
        unlocked_at=now,
        expires_at=now + timedelta(seconds=_idle_seconds),
    )
    return _session


def touch_session() -> None:
    global _session
    if _session is None:
        return
    now = datetime.now(timezone.utc)
    _session.expires_at = now + timedelta(seconds=_idle_seconds)


def lock_session() -> None:
    global _session
    _session = None


def get_vmk() -> Optional[bytes]:
    global _session
    if _session is None:
        return None
    now = datetime.now(timezone.utc)
    if now >= _session.expires_at:
        _session = None
        return None
    touch_session()
    return _session.vmk


def session_status() -> dict[str, object]:
    if _session is None:
        return {"locked": True}
    now = datetime.now(timezone.utc)
    if now >= _session.expires_at:
        lock_session()
        return {"locked": True}
    return {
        "locked": False,
        "unlocked_at": _session.unlocked_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": _session.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
