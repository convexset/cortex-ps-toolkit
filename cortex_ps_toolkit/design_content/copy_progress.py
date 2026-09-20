"""Progress events for per-item copy notifications."""

from __future__ import annotations

from typing import Any, Callable, Optional

_SKIP_ACTIONS = frozenset({
    "skip",
    "skipped",
    "missing",
    "conflict",
    "blocked_pack",
    "blocked_non_copyable",
    "incompatible",
})
_SKIP_STATUSES = frozenset({"skipped", "conflict", "missing", "failed"})
_SUCCESS_STATUSES = frozenset({"copied", "updated"})
_SUCCESS_ACTIONS = frozenset({"copy", "update"})


def copy_entry_succeeded(entry: dict[str, Any]) -> bool:
    """Return True when a copy result entry represents a successful write."""
    if not isinstance(entry, dict):
        return False
    status = entry.get("status")
    action = entry.get("action")
    if status in _SKIP_STATUSES or action in _SKIP_ACTIONS:
        return False
    if isinstance(status, int):
        return 200 <= status < 300
    if status in _SUCCESS_STATUSES or action in _SUCCESS_ACTIONS:
        return True
    return False


def notify_item_copied(
    on_progress: Optional[Callable[[dict[str, Any]], None]],
    asset: str,
    entry: dict[str, Any],
) -> None:
    """Emit a progress event when an item copy succeeds."""
    if not on_progress or not copy_entry_succeeded(entry):
        return
    on_progress({"phase": "item_copied", "asset": asset, "entry": dict(entry)})
