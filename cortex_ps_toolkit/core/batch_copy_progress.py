"""Shared staged progress and step events for linear batch copy operations."""

from __future__ import annotations

from typing import Any, Callable, Optional

from .staged_progress import StagedProgressReporter

ProgressCallback = Callable[[dict[str, Any]], None]

STAGE_PLAN = "Prepare Copy Plan"
STAGE_ITEMS = "Copy Items"
STAGE_CACHE_REFRESH = "Target Cache Refresh"
STAGE_FINALIZE = "Finalize Copy"


def batch_copy_stages(*, with_cache_refresh: bool = True) -> list[str]:
    if with_cache_refresh:
        return [STAGE_PLAN, STAGE_ITEMS, STAGE_CACHE_REFRESH]
    return [STAGE_PLAN, STAGE_ITEMS, STAGE_FINALIZE]


def make_batch_copy_progress(
    *,
    title: str,
    operation: str,
    on_progress: Optional[ProgressCallback] = None,
    with_cache_refresh: bool = True,
) -> StagedProgressReporter:
    return StagedProgressReporter(
        batch_copy_stages(with_cache_refresh=with_cache_refresh),
        title=title,
        on_progress=on_progress,
        operation=operation,
    )


def emit_copy_item_step(
    on_progress: Optional[ProgressCallback],
    *,
    source: str,
    target: str,
    item_label: str,
    name: str,
    index: int,
    total: int,
    item_id: str = "",
) -> None:
    if not on_progress:
        return
    on_progress({
        "phase": "step",
        "current": {
            "source": source,
            "target": target,
            "step": name,
            "item_id": item_id or None,
            "status": f"{index}/{total}",
        },
        "item_label": item_label,
        "index": index,
        "total": total,
    })


def chain_progress(*handlers: Optional[ProgressCallback]) -> Optional[ProgressCallback]:
    callbacks = [handler for handler in handlers if handler]
    if not callbacks:
        return None

    def combined(event: dict[str, Any]) -> None:
        for handler in callbacks:
            handler(event)

    return combined
