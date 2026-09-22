"""Staged progress events and WebSocket toast notifications for long operations."""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

ProgressCallback = Callable[[dict[str, Any]], None]


def format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def publish_staged_progress(
    *,
    title: str,
    stage: int,
    stage_total: int,
    stage_label: str,
    elapsed_seconds: float,
    auto_dismiss_ms: int = 5000,
    level: str = "info",
) -> None:
    try:
        from ..server.events import publish_notification

        message = (
            f"Completed Stage {stage}/{stage_total} {stage_label} "
            f"(Time Elapsed: {format_elapsed(elapsed_seconds)})"
        )
        publish_notification(message, level=level, title=title, auto_dismiss_ms=auto_dismiss_ms)
    except Exception:
        pass


class StagedProgressReporter:
    """Emit numbered stage-complete events for one long-running operation."""

    def __init__(
        self,
        stage_labels: list[str],
        *,
        title: str,
        on_progress: Optional[ProgressCallback] = None,
        operation: str = "",
        progress_auto_dismiss_ms: int = 5000,
    ) -> None:
        self.stage_labels = list(stage_labels)
        self.stage_total = max(len(self.stage_labels), 1)
        self.title = title
        self.on_progress = on_progress
        self.operation = operation
        self.progress_auto_dismiss_ms = progress_auto_dismiss_ms
        self._started = time.monotonic()
        self._index = 0

    @property
    def elapsed_seconds(self) -> float:
        return round(time.monotonic() - self._started, 1)

    def complete_stage(self, label: Optional[str] = None) -> None:
        self._index += 1
        stage = min(self._index, self.stage_total)
        stage_label = label or self.stage_labels[stage - 1] if stage - 1 < len(self.stage_labels) else "Step"
        event = {
            "phase": "stage_complete",
            "stage": stage,
            "stage_total": self.stage_total,
            "stage_label": stage_label,
            "step": stage_label,
            "elapsed_seconds": self.elapsed_seconds,
            "operation": self.operation,
        }
        if self.on_progress:
            self.on_progress(event)
        else:
            publish_staged_progress(
                title=self.title,
                stage=stage,
                stage_total=self.stage_total,
                stage_label=stage_label,
                elapsed_seconds=self.elapsed_seconds,
                auto_dismiss_ms=self.progress_auto_dismiss_ms,
            )
