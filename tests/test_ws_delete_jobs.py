"""Smoke tests for WebSocket delete job dispatch."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from cortex_ps_toolkit.server import ws


def _close_scheduled_coro(coro) -> None:
    coro.close()


@pytest.mark.asyncio
async def test_dispatch_design_content_delete_starts_task() -> None:
    with patch.object(ws.asyncio, "create_task", side_effect=_close_scheduled_coro) as mock_create:
        await ws._dispatch_job({
            "job_id": "job-1",
            "action": "design_content.delete",
            "payload": {"profile": "lab", "asset": "layouts", "item_ids": ["L1"]},
        })
    mock_create.assert_called_once()
    assert mock_create.call_args[0][0].__name__ == "_run_design_content_delete"


@pytest.mark.asyncio
async def test_dispatch_platform_admin_indicator_delete_starts_task() -> None:
    with patch.object(ws.asyncio, "create_task", side_effect=_close_scheduled_coro) as mock_create:
        await ws._dispatch_job({
            "job_id": "job-2",
            "action": "platform_admin.indicator_delete",
            "payload": {"profile": "lab", "ids": ["114"]},
        })
    mock_create.assert_called_once()
    assert mock_create.call_args[0][0].__name__ == "_run_platform_admin_indicator_delete"


@pytest.mark.asyncio
async def test_run_design_content_delete_broadcasts_completion() -> None:
    with patch.object(ws, "broadcast", new_callable=AsyncMock) as mock_broadcast, patch.object(
        ws,
        "delete_assets",
        return_value={"profile": "lab", "asset": "layouts", "results": []},
    ):
        await ws._run_design_content_delete("job-3", {
            "profile": "lab",
            "asset": "layouts",
            "item_ids": ["L1"],
        })

    completed = [call.args[0] for call in mock_broadcast.await_args_list if call.args[0].get("type") == "job.completed"]
    assert completed
    assert completed[-1]["action"] == "design_content.delete"
