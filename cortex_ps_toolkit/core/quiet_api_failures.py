"""Suppress user-facing error toasts for expected, handled API write failures."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Iterator

_suppress_failure_toast = contextvars.ContextVar("suppress_tenant_api_failure_toast", default=False)


def tenant_api_failure_toast_suppressed() -> bool:
    return bool(_suppress_failure_toast.get())


@contextmanager
def quiet_expected_api_failure() -> Iterator[None]:
    """While active, HTTP failures still raise ``TenantApiError`` but skip error toasts."""
    token = _suppress_failure_toast.set(True)
    try:
        yield
    finally:
        _suppress_failure_toast.reset(token)
