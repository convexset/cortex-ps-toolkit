"""In-process event bus for WebSocket clients."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

_subscribers: set[Any] = set()
_loop: Optional[asyncio.AbstractEventLoop] = None


def bind_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def subscribe(websocket: Any) -> None:
    _subscribers.add(websocket)


def unsubscribe(websocket: Any) -> None:
    _subscribers.discard(websocket)


async def broadcast(message: dict[str, Any]) -> None:
    if not _subscribers:
        return
    payload = json.dumps(message, default=str)
    dead: list[Any] = []
    for websocket in list(_subscribers):
        try:
            await websocket.send_text(payload)
        except Exception:
            dead.append(websocket)
    for websocket in dead:
        unsubscribe(websocket)


def publish(message: dict[str, Any]) -> None:
    """Thread-safe publish from sync code (copy workflows, cache refresh)."""
    if _loop is None or not _loop.is_running():
        return
    asyncio.run_coroutine_threadsafe(broadcast(message), _loop)


def publish_notification(
    message: str,
    *,
    level: str = "info",
    auto_dismiss_ms: int = 5000,
    title: Optional[str] = None,
) -> None:
    publish({
        "type": "notification",
        "level": level,
        "title": title,
        "message": message,
        "autoDismissMs": auto_dismiss_ms,
    })


def publish_log(level: str, message: str) -> None:
    publish({"type": "log", "level": level, "message": message})
