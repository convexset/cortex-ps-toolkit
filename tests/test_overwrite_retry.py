"""Delete-then-recreate retry for overwrite writes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cortex_ps_toolkit.content.overwrite_retry import (
    execute_overwrite_write,
    is_overwrite_recoverable_error,
    notify_overwrite_retry_started,
)
from cortex_ps_toolkit.core.client import TenantApiError


def test_is_overwrite_recoverable_error_detects_optimistic_lock() -> None:
    exc = TenantApiError(
        "write failed",
        status_code=400,
        body={"id": "errOptimisticLock", "error": "Optimistic lock error"},
    )
    assert is_overwrite_recoverable_error(exc) is True


def test_execute_overwrite_write_retries_after_optimistic_lock() -> None:
    calls = {"write": 0, "delete": 0}
    retry_events: list[dict] = []

    def write() -> str:
        calls["write"] += 1
        if calls["write"] == 1:
            raise TenantApiError(
                "fail",
                status_code=400,
                body={"id": "errOptimisticLock"},
            )
        return "ok"

    def delete() -> None:
        calls["delete"] += 1

    with patch("cortex_ps_toolkit.content.overwrite_retry.time.sleep"):
        with patch("cortex_ps_toolkit.content.overwrite_retry.notify_overwrite_retry_started"):
            result, meta = execute_overwrite_write(
                action="update",
                write=write,
                delete=delete,
                on_retry=retry_events.append,
            )

    assert result == "ok"
    assert calls["write"] == 2
    assert calls["delete"] == 1
    assert meta and meta.get("overwrite_retry") == "delete_then_create"
    assert retry_events and retry_events[0].get("phase") == "overwrite_retry"


@patch("cortex_ps_toolkit.server.events.publish_notification")
def test_notify_overwrite_retry_started_uses_warning_toast(mock_publish) -> None:
    notify_overwrite_retry_started(
        TenantApiError("x", status_code=400, body={"detail": "Optimistic lock error"}),
    )
    mock_publish.assert_called_once()
    _args, kwargs = mock_publish.call_args
    assert kwargs["level"] == "warning"
    assert kwargs["auto_dismiss_ms"] > 5000


def test_execute_overwrite_write_copy_skips_delete() -> None:
    result, meta = execute_overwrite_write(
        action="copy",
        write=lambda: "created",
        delete=lambda: (_ for _ in ()).throw(AssertionError("no delete")),
    )
    assert result == "created"
    assert meta is None
