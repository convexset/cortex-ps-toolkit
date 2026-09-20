"""Refactor extract eligibility checks for analysis UI (wraps playbook-utils graph rules)."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


def _task_sort_key(task_id: str) -> tuple[int, str]:
    text = str(task_id)
    return (0, f"{int(text):020d}") if text.isdigit() else (1, text)


def _import_graph():
    from playbook_utils.graph import check_cluster_extract, check_combined_extract, check_potential_root
    from playbook_utils.keys import inner_task, playbook_tasks, task_name, task_type

    return check_cluster_extract, check_combined_extract, check_potential_root, inner_task, playbook_tasks, task_name, task_type


def _truncate_description(text: str, *, max_len: int = 72) -> str:
    collapsed = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 1].rstrip() + "…"


def _task_description(node: Mapping[str, Any]) -> str:
    _, _, _, inner_task, _, _, _ = _import_graph()
    inner = inner_task(node)
    return str(inner.get("description") or node.get("description") or "")


def build_refactor_task_catalog(playbook: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Per-task metadata for refactor dropdowns (root playbook)."""
    _, _, check_potential_root, _, playbook_tasks, task_name, task_type = _import_graph()

    catalog: list[dict[str, Any]] = []
    tasks = playbook_tasks(playbook)
    for task_id in sorted(tasks.keys(), key=_task_sort_key):
        node = tasks[task_id]
        ttype = str(task_type(node) or "unknown")
        if ttype == "start":
            continue
        description = _task_description(node)
        check = check_potential_root(playbook, str(task_id))
        catalog.append(
            {
                "id": str(task_id),
                "label": str(task_name(node) or task_id),
                "task_type": ttype,
                "description": description,
                "description_short": _truncate_description(description),
                "leaf_ok": bool(check.ok),
                "leaf_reasons": list(check.reasons),
            }
        )
    return catalog


def validate_leaf_extract(
    playbook: Mapping[str, Any],
    task_id: str,
    *,
    other_leaf_task_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate one leaf extract, including multi-leaf conflicts when others are provided."""
    _, check_combined_extract, check_potential_root, _, playbook_tasks, task_name, task_type = _import_graph()

    tid = str(task_id or "").strip()
    if not tid:
        return {"ok": False, "reasons": ["Select a task"]}

    others = [str(item).strip() for item in (other_leaf_task_ids or []) if str(item).strip() and str(item) != tid]
    task_ids = others + [tid]
    combined = check_combined_extract(playbook, task_ids, [])

    root_check = check_potential_root(playbook, tid)
    tasks = playbook_tasks(playbook)
    node = tasks.get(tid)
    label = task_name(node) if node else tid
    ttype = task_type(node) if node else "unknown"

    return {
        "ok": bool(combined.ok),
        "reasons": list(combined.reasons),
        "task_id": tid,
        "label": label,
        "task_type": ttype,
        "leaf_ok": bool(root_check.ok),
        "leaf_reasons": list(root_check.reasons),
    }


def validate_cluster_extract(
    playbook: Mapping[str, Any],
    start_id: str,
    end_id: str,
) -> dict[str, Any]:
    """Validate START:END cluster spec; returns check dict with ok + reasons."""
    check_cluster_extract, *_ = _import_graph()
    start = str(start_id or "").strip()
    end = str(end_id or "").strip()
    if not start or not end:
        return {"ok": False, "reasons": ["Select both start and end tasks"]}
    if start.isdigit() and end.isdigit() and int(start) >= int(end):
        return {"ok": False, "reasons": ["START must be less than END"]}
    result = check_cluster_extract(playbook, start, end)
    payload = result.to_dict()
    payload["start_id"] = start
    payload["end_id"] = end
    return payload
