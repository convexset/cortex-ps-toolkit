"""Delete-then-recreate retry when overwrite writes fail (e.g. optimistic lock)."""

from __future__ import annotations

import time
from typing import Any, Callable, Optional, TypeVar

from ..core.client import TenantApiError
from ..core.quiet_api_failures import quiet_expected_api_failure
from ..ops_log import op_info

OVERWRITE_RETRY_DELAY_SEC = 0.5
OVERWRITE_RETRY_WARNING_TOAST_MS = 12_000

T = TypeVar("T")


def is_overwrite_recoverable_error(exc: BaseException) -> bool:
    if not isinstance(exc, TenantApiError):
        return False
    status = exc.status_code
    if status not in (400, 409, 422):
        return False
    body = exc.body
    text_parts: list[str] = [str(exc)]
    if isinstance(body, dict):
        for key in ("id", "title", "detail", "error", "message"):
            val = body.get(key)
            if val:
                text_parts.append(str(val))
    elif body is not None:
        text_parts.append(str(body))
    blob = " ".join(text_parts).lower()
    markers = (
        "optimistic lock",
        "erroptimisticlock",
        "do not match",
        "version",
        "already exists",
        "duplicate",
    )
    return any(marker in blob for marker in markers)


def _safe_delete(delete: Callable[[], Any]) -> None:
    try:
        delete()
    except TenantApiError as exc:
        if exc.status_code in (404, 400):
            op_info("Overwrite retry delete returned HTTP %s (continuing): %s", exc.status_code, exc)
            return
        raise
    except KeyError:
        return


def notify_overwrite_retry_started(exc: TenantApiError, *, title: str = "Copy overwrite retry") -> None:
    """User-visible warning: first overwrite failed; delete + retry is in progress."""
    detail = ""
    if isinstance(exc.body, dict):
        detail = str(exc.body.get("detail") or exc.body.get("error") or exc.body.get("title") or "").strip()
    message = (
        "The initial overwrite failed (often an optimistic-lock / version mismatch). "
        "Deleting the existing item on the target and retrying the upload."
    )
    if detail:
        message = f"{message} ({detail})"
    try:
        from ..server.events import publish_notification

        publish_notification(
            message,
            level="warning",
            title=title,
            auto_dismiss_ms=OVERWRITE_RETRY_WARNING_TOAST_MS,
        )
    except Exception:
        pass
    op_info("Overwrite retry: %s", message)


def execute_overwrite_write(
    *,
    action: str,
    write: Callable[[], T],
    delete: Callable[[], Any],
    on_retry: Optional[Callable[[dict[str, Any]], None]] = None,
) -> tuple[T, dict[str, Any] | None]:
    """Run write; on recoverable failure during update, delete target, pause, write again."""
    if action != "update":
        return write(), None
    with quiet_expected_api_failure():
        try:
            return write(), None
        except TenantApiError as exc:
            if not is_overwrite_recoverable_error(exc):
                raise
            retry_meta: dict[str, Any] = {
                "phase": "overwrite_retry",
                "overwrite_retry": "delete_then_create",
                "first_error": str(exc),
                "status_code": exc.status_code,
            }
            notify_overwrite_retry_started(exc)
            if on_retry:
                on_retry(retry_meta)
            target_label = str(getattr(exc, "message", None) or exc)
            op_info(
                "Overwrite write failed (%s); deleting target, waiting %.1fs, then creating again",
                target_label,
                OVERWRITE_RETRY_DELAY_SEC,
            )
            _safe_delete(delete)
            time.sleep(OVERWRITE_RETRY_DELAY_SEC)
            result = write()
            return result, retry_meta
