"""WebSocket toast notifications for successful delete operations."""

from __future__ import annotations

from typing import Any

from .events import publish_notification

_LABEL_KEYS = (
    "name",
    "target_name",
    "source_name",
    "integration_id",
    "list_id",
    "playbook_id",
    "script_id",
    "item_id",
    "key_id",
    "id",
)


def _entry_label(entry: dict[str, Any]) -> str:
    for key in _LABEL_KEYS:
        value = entry.get(key)
        if value not in (None, ""):
            return str(value)
    return "item"


def delete_entry_succeeded(entry: dict[str, Any]) -> bool:
    """True when a delete result row represents a successful removal."""
    status = entry.get("status")
    if status == "deleted":
        return True
    if isinstance(status, int):
        return 200 <= status < 300
    if isinstance(status, str) and status.isdigit():
        code = int(status)
        return 200 <= code < 300
    return False


def _iter_delete_result_entries(result: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Flatten delete results into (asset_label, entry) pairs."""
    pairs: list[tuple[str, dict[str, Any]]] = []
    asset = str(result.get("asset") or "")
    assets = result.get("assets")
    if isinstance(assets, dict):
        for asset_name, asset_result in assets.items():
            if not isinstance(asset_result, dict):
                continue
            for entry in asset_result.get("results") or []:
                if isinstance(entry, dict):
                    pairs.append((str(asset_name), entry))
        return pairs
    for entry in result.get("results") or []:
        if isinstance(entry, dict):
            pairs.append((asset, entry))
    return pairs


def publish_item_deleted_notification(
    entry: dict[str, Any],
    *,
    asset: str = "",
    profile: str = "",
    title: str = "Delete",
    auto_dismiss_ms: int = 5000,
) -> None:
    """Publish a success toast for one deleted item (5s auto-dismiss)."""
    if not delete_entry_succeeded(entry):
        return
    label = _entry_label(entry)
    prefix = f"{profile} · " if profile else ""
    item_text = f"{asset}: {label}" if asset else label
    message = f"{prefix}Deleted: {item_text}" if prefix else f"Deleted: {item_text}"
    publish_notification(message, level="success", title=title, auto_dismiss_ms=auto_dismiss_ms)


def publish_delete_success_notifications(
    result: dict[str, Any],
    *,
    title: str,
    profile: str = "",
    asset: str = "",
) -> None:
    """Publish one success toast per deleted item (5s auto-dismiss each)."""
    published = 0
    resolved_profile = str(result.get("profile") or profile or "")
    resolved_asset = str(result.get("asset") or asset or "")
    for entry_asset, entry in _iter_delete_result_entries(result):
        if delete_entry_succeeded(entry):
            publish_item_deleted_notification(
                entry,
                asset=entry_asset or resolved_asset,
                profile=resolved_profile,
                title=title,
            )
            published += 1
    if published:
        return
    prefix = f"{resolved_profile} · " if resolved_profile else ""
    message = f"{prefix}No items were deleted." if prefix else "No items were deleted."
    publish_notification(message, level="warning", title=title, auto_dismiss_ms=5000)
