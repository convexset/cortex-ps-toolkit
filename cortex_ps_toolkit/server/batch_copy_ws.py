"""WebSocket jobs for standard batch copy operations (lists, scripts, playbooks)."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from .copy_progress_http import publish_standard_copy_outcome
from .events import publish_notification


async def run_batch_copy_job(
    job_id: str,
    payload: dict[str, Any],
    *,
    action: str,
    title: str,
    progress_title: str,
    ids_key: str,
    copy_fn: Callable[..., dict[str, Any]],
    broadcast: Callable[..., Any],
    publish_job_progress: Callable[[str, str, dict[str, Any]], None],
) -> None:
    source = str(payload.get("source_profile") or "")
    target = str(payload.get("target_profile") or "")
    item_ids = [str(item) for item in (payload.get(ids_key) or [])]
    if not source or not target or not item_ids:
        await broadcast({
            "type": "job.failed",
            "job_id": job_id,
            "action": action,
            "error": f"source_profile, target_profile, {ids_key} required",
        })
        return

    await broadcast({
        "type": "job.started",
        "job_id": job_id,
        "action": action,
        "payload": payload,
    })
    publish_notification(
        f"{title}: {source} → {target} ({len(item_ids)} item(s))…",
        level="info",
        title=progress_title,
        auto_dismiss_ms=5000,
    )

    def on_progress(event: dict[str, Any]) -> None:
        publish_job_progress(job_id, action, event)

    try:
        result = await asyncio.to_thread(
            copy_fn,
            source,
            target,
            item_ids,
            overwrite=bool(payload.get("overwrite")),
            stop_on_conflict=bool(payload.get("stop_on_conflict")),
            on_progress=on_progress,
        )
        await broadcast({
            "type": "job.completed",
            "job_id": job_id,
            "action": action,
            "result": result,
        })
        publish_standard_copy_outcome(result, title=title, source=source, target=target)
    except Exception as exc:
        await broadcast({
            "type": "job.failed",
            "job_id": job_id,
            "action": action,
            "error": str(exc),
        })
        publish_notification(
            f"{title} failed: {exc}",
            level="error",
            title=title,
            auto_dismiss_ms=0,
        )
