"""WebSocket jobs for standard batch copy operations (lists, scripts, playbooks, bundles)."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from ..content.copy_plan_params import copy_kwargs_from_body
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
    optional_bool_kwargs: frozenset[str] = frozenset(),
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
        copy_kw = copy_kwargs_from_body(payload)
        extra_kwargs = {key: bool(payload.get(key)) for key in optional_bool_kwargs}
        result = await asyncio.to_thread(
            copy_fn,
            source,
            target,
            item_ids,
            on_progress=on_progress,
            **copy_kw,
            **extra_kwargs,
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


async def run_bundle_copy_job(
    job_id: str,
    payload: dict[str, Any],
    *,
    copy_fn: Callable[..., dict[str, Any]],
    broadcast: Callable[..., Any],
    publish_job_progress: Callable[[str, str, dict[str, Any]], None],
) -> None:
    source = str(payload.get("source_profile") or "")
    target = str(payload.get("target_profile") or "")
    items = payload.get("items") or []
    if not source or not target or not items:
        await broadcast({
            "type": "job.failed",
            "job_id": job_id,
            "action": "bundles.copy",
            "error": "source_profile, target_profile, items required",
        })
        return

    action = "bundles.copy"
    title = "Bundle copy"
    await broadcast({
        "type": "job.started",
        "job_id": job_id,
        "action": action,
        "payload": payload,
    })
    publish_notification(
        f"{title}: {source} → {target} ({len(items)} basket item(s))…",
        level="info",
        title="Bundle copy",
        auto_dismiss_ms=5000,
    )

    def on_progress(event: dict[str, Any]) -> None:
        publish_job_progress(job_id, action, event)

    rename_map_raw = payload.get("rename_map") or {}
    rename_map = (
        {str(k): str(v) for k, v in rename_map_raw.items()}
        if isinstance(rename_map_raw, dict)
        else {}
    )
    try:
        result = await asyncio.to_thread(
            copy_fn,
            source,
            target,
            items,
            overwrite=bool(payload.get("overwrite")),
            stop_on_conflict=bool(payload.get("stop_on_conflict")),
            copy_mode=payload.get("copy_mode"),
            rename_suffix=str(payload.get("rename_suffix") or ""),
            rename_map=rename_map,
            shallow_playbooks=bool(payload.get("shallow_playbooks", True)),
            post_copy_diff=bool(payload.get("post_copy_diff")),
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
