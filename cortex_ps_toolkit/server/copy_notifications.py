"""WebSocket toast notifications summarising successful copy operations."""

from __future__ import annotations

from typing import Any

from ..design_content.copy_progress import copy_entry_succeeded
from .events import publish_notification
_LABEL_KEYS = (
    "target_name",
    "name",
    "source_name",
    "source_id",
    "target_id",
    "integration_id",
    "list_id",
    "playbook_id",
    "script_id",
    "id",
)


def _entry_label(entry: dict[str, Any]) -> str:
    for key in _LABEL_KEYS:
        value = entry.get(key)
        if value not in (None, ""):
            return str(value)
    return "item"


def copied_item_labels(result: dict[str, Any]) -> list[str]:
    """Return human-readable labels for items copied successfully."""
    labels: list[str] = []
    assets = result.get("assets")
    if isinstance(assets, dict):
        for asset, asset_result in assets.items():
            if not isinstance(asset_result, dict):
                continue
            for label in copied_item_labels(asset_result):
                labels.append(f"{asset}: {label}")
        return labels

    for _asset, entry in _iter_copy_result_entries(result):
        if copy_entry_succeeded(entry):
            label = _entry_label(entry)
            labels.append(f"{_asset}: {label}" if _asset else label)
    return labels


def _absorb_copy_result_entries(container: dict[str, Any], *, asset_label: str = "") -> list[tuple[str, dict[str, Any]]]:
    pairs: list[tuple[str, dict[str, Any]]] = []
    for entry in container.get("results") or []:
        if isinstance(entry, dict):
            pairs.append((asset_label, entry))
    nested_assets = container.get("assets")
    if isinstance(nested_assets, dict):
        for asset, asset_result in nested_assets.items():
            if isinstance(asset_result, dict):
                pairs.extend(_absorb_copy_result_entries(asset_result, asset_label=str(asset)))
    return pairs


def _flatten_batch_copy_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten list or nested phase/asset copy payloads into per-item rows."""
    pairs = _iter_copy_result_entries(result)
    return [entry for _asset, entry in pairs]


def _iter_copy_result_entries(result: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Flatten copy results into (asset_label, entry) pairs."""
    pairs: list[tuple[str, dict[str, Any]]] = []
    assets = result.get("assets")
    if isinstance(assets, dict):
        for asset, asset_result in assets.items():
            if not isinstance(asset_result, dict):
                continue
            pairs.extend(_absorb_copy_result_entries(asset_result, asset_label=str(asset)))
        return pairs
    raw_results = result.get("results")
    if isinstance(raw_results, dict):
        for phase, phase_result in raw_results.items():
            if isinstance(phase_result, dict):
                pairs.extend(_absorb_copy_result_entries(phase_result, asset_label=str(phase)))
        return pairs
    if isinstance(raw_results, list):
        for entry in raw_results:
            if isinstance(entry, dict):
                pairs.append(("", entry))
    return pairs


def publish_item_copied_notification(
    entry: dict[str, Any],
    *,
    asset: str = "",
    source: str = "",
    target: str = "",
    title: str = "Object Bundle copy",
    auto_dismiss_ms: int = 5000,
) -> None:
    """Publish a success toast for one copied item (5s auto-dismiss)."""
    if not copy_entry_succeeded(entry):
        return
    label = _entry_label(entry)
    route = f"{source} → {target}" if source and target else ""
    item_text = f"{asset}: {label}" if asset else label
    message = f"{route} · Copied: {item_text}" if route else f"Copied: {item_text}"
    publish_notification(message, level="success", title=title, auto_dismiss_ms=auto_dismiss_ms)


def maybe_publish_item_copied_from_progress(
    event: dict[str, Any],
    *,
    source: str,
    target: str,
    title: str = "Object Bundle copy",
) -> None:
    """Publish a per-item toast when an Object Bundle copy progress event succeeds."""
    if event.get("phase") != "item_copied":
        return
    entry = event.get("entry")
    if not isinstance(entry, dict):
        return
    publish_item_copied_notification(
        entry,
        asset=str(event.get("asset") or ""),
        source=source,
        target=target,
        title=title,
    )


def publish_batch_copy_complete_notification(
    result: dict[str, Any],
    *,
    source: str,
    target: str,
    title: str = "Copy",
    auto_dismiss_ms: int = 0,
) -> None:
    """Summary banner after a standard batch copy (lists, scripts, playbooks, IOCs, …)."""
    results = _flatten_batch_copy_rows(result)
    ok = sum(1 for row in results if copy_entry_succeeded(row))
    failed = [row for row in results if row.get("status") == "failed"]
    skipped = sum(
        1
        for row in results
        if row.get("status") in ("skipped", "conflict", "blocked") or row.get("action") in ("skip", "conflict")
    )
    route = f"{source} → {target}" if source and target else ""
    level = "success" if ok and not failed else "warning" if ok else "error"
    message = f"{route}: {title.lower()} finished — {ok} copied/updated"
    if skipped:
        message += f", {skipped} skipped"
    if failed:
        message += f", {len(failed)} failed"
    publish_notification(message, level=level, title=title, auto_dismiss_ms=auto_dismiss_ms)


def publish_deep_copy_complete_notification(
    result: dict[str, Any],
    *,
    source: str,
    target: str,
    title: str = "Deep playbook copy",
    auto_dismiss_ms: int = 0,
) -> None:
    if result.get("aborted"):
        publish_notification(
            result.get("reason") or "Deep playbook copy was aborted.",
            level="error",
            title=title,
            auto_dismiss_ms=0,
        )
        return
    script_results = result.get("script_results") or []
    playbook_results = result.get("playbook_results") or []
    scripts_ok = sum(1 for row in script_results if row.get("status") in ("copied", "updated", "skipped"))
    playbooks_ok = sum(1 for row in playbook_results if row.get("status") in ("copied", "updated", "skipped"))
    failed = [row for row in playbook_results if row.get("status") == "failed"]
    binding_issues = result.get("binding_issues") or []
    level = "success" if not failed and not binding_issues else "error"
    message = (
        f"{source} → {target}: deep copy finished — "
        f"{scripts_ok} script(s), {playbooks_ok} playbook(s) processed."
    )
    if failed:
        message += f" {len(failed)} playbook(s) failed."
    if binding_issues:
        message += f" {len(binding_issues)} binding issue(s)."
    publish_notification(message, level=level, title=title, auto_dismiss_ms=auto_dismiss_ms)


def publish_object_bundle_complete_notification(
    result: dict[str, Any],
    *,
    source: str,
    target: str,
    title: str = "Object Bundle copy",
    auto_dismiss_ms: int = 0,
) -> None:
    """Publish a summary toast after Object Bundle copy without re-listing each item."""
    copied = copied_item_labels(result)
    route = f"{source} → {target}" if source and target else ""
    if not copied:
        message = f"{route}: no items were copied." if route else "No items were copied."
        publish_notification(message, level="warning", title=title, auto_dismiss_ms=auto_dismiss_ms)
        return
    count_label = "item" if len(copied) == 1 else "items"
    prefix = f"{route} · " if route else ""
    message = f"{prefix}Object Bundle copy complete ({len(copied)} {count_label})"
    publish_notification(message, level="success", title=title, auto_dismiss_ms=auto_dismiss_ms)


def publish_copy_success_notifications(
    result: dict[str, Any],
    *,
    title: str,
    source: str = "",
    target: str = "",
) -> None:
    """Publish one success toast per copied item (5s auto-dismiss each)."""
    published = 0
    for asset, entry in _iter_copy_result_entries(result):
        if copy_entry_succeeded(entry):
            publish_item_copied_notification(
                entry,
                asset=asset,
                source=source,
                target=target,
                title=title,
            )
            published += 1
    if published:
        return
    route = f"{source} → {target}" if source and target else ""
    message = f"{route}: no items were copied." if route else "No items were copied."
    publish_notification(message, level="warning", title=title, auto_dismiss_ms=5000)
