"""Progress reporting and heartbeat for long-running synchronous operations."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional

ProgressCallback = Callable[[dict[str, Any]], None]


class LongOperationProgress:
    """Track in-flight steps and emit periodic heartbeat progress events."""

    def __init__(
        self,
        on_progress: Optional[ProgressCallback] = None,
        *,
        heartbeat_seconds: float = 30.0,
        action: str = "",
    ) -> None:
        self.on_progress = on_progress
        self.heartbeat_seconds = heartbeat_seconds
        self.action = action
        self._started = time.monotonic()
        self._current: dict[str, Any] = {}
        self._in_flight: list[dict[str, Any]] = []
        self._completed: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def elapsed_seconds(self) -> float:
        return round(time.monotonic() - self._started, 1)

    def set_current(self, **state: Any) -> None:
        with self._lock:
            self._current = dict(state)
        self._emit(phase="step", **state)

    def set_in_flight(self, items: list[dict[str, Any]]) -> None:
        with self._lock:
            self._in_flight = list(items)

    def mark_completed(self, item: dict[str, Any]) -> None:
        with self._lock:
            self._completed.append(dict(item))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "action": self.action,
                "elapsed_seconds": self.elapsed_seconds,
                "current": dict(self._current),
                "in_flight": list(self._in_flight),
                "completed_count": len(self._completed),
            }

    def _emit(self, *, phase: str, **extra: Any) -> None:
        if not self.on_progress:
            return
        payload = self.snapshot()
        payload["phase"] = phase
        payload.update(extra)
        self.on_progress(payload)

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            self._emit(phase="heartbeat")

    def __enter__(self) -> LongOperationProgress:
        if self.on_progress and self.heartbeat_seconds > 0:
            self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self._thread.start()
        self._emit(phase="started")
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        self._emit(phase="finished", ok=exc is None, error=str(exc) if exc else None)
