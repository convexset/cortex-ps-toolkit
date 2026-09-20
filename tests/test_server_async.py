from __future__ import annotations

import asyncio
import time

import pytest

from cortex_ps_toolkit.server.common import run_sync


def _sleep_brief() -> float:
    time.sleep(0.05)
    return time.monotonic()


@pytest.mark.asyncio
async def test_run_sync_allows_concurrent_work() -> None:
    start = time.monotonic()
    await asyncio.gather(run_sync(_sleep_brief), run_sync(_sleep_brief))
    elapsed = time.monotonic() - start
    assert elapsed < 0.09
