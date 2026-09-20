"""Tests for long-operation progress heartbeats."""

from __future__ import annotations

import time

from cortex_ps_toolkit.core.long_op_progress import LongOperationProgress


def test_long_operation_progress_emits_heartbeat_and_steps() -> None:
    events: list[dict] = []

    with LongOperationProgress(events.append, heartbeat_seconds=0.05, action="test.action") as progress:
        progress.set_current(step="alpha")
        progress.set_in_flight([{"item": "a", "status": "running"}])
        time.sleep(0.12)
        progress.set_current(step="beta")

    phases = [event.get("phase") for event in events]
    assert "started" in phases
    assert "step" in phases
    assert "heartbeat" in phases
    assert "finished" in phases
    heartbeat = next(event for event in events if event.get("phase") == "heartbeat")
    assert heartbeat["in_flight"]
    assert heartbeat["elapsed_seconds"] >= 0
