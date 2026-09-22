"""HTTP copy handlers: staged toasts from progress events and completion banners."""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..core.batch_copy_progress import ProgressCallback
from ..core.staged_progress import publish_staged_progress
from .copy_notifications import publish_batch_copy_complete_notification
from .events import publish_notification


def http_staged_copy_progress(title: str) -> ProgressCallback:
    """Emit self-dismissing stage toasts for synchronous HTTP copy requests."""

    def on_progress(event: dict[str, Any]) -> None:
        if event.get("phase") != "stage_complete":
            return
        publish_staged_progress(
            title=f"{title} Progress",
            stage=int(event["stage"]),
            stage_total=int(event["stage_total"]),
            stage_label=str(event.get("stage_label") or event.get("step") or "Step"),
            elapsed_seconds=float(event.get("elapsed_seconds") or 0),
        )

    return on_progress


def publish_standard_copy_outcome(
    result: dict[str, Any],
    *,
    title: str,
    source: str,
    target: str,
) -> None:
    """Persistent banner for batch copy completion, abort, or execution failure."""
    if result.get("aborted"):
        publish_notification(
            str(result.get("reason") or f"{title} was aborted."),
            level="error",
            title=title,
            auto_dismiss_ms=0,
        )
        return
    if result.get("executed") is False:
        message = result.get("error") or result.get("halt_reason") or f"{title} finished with issues."
        publish_notification(
            str(message),
            level="error",
            title=title,
            auto_dismiss_ms=0,
        )
        return
    publish_batch_copy_complete_notification(
        result,
        title=title,
        source=source,
        target=target,
    )
