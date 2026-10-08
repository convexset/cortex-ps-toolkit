"""Versioned operation plan envelope for copy preview endpoints."""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional, Sequence

from .copy_modes import CopyMode, plan_would_abort
from .copy_plan_params import parse_copy_mode

PLAN_VERSION = 1


def _action_to_summary_action(action: str) -> str:
    if action == "update":
        return "update"
    if action in ("copy", "copy_as_new"):
        return "create"
    if action == "skip":
        return "skip"
    if action in ("conflict", "blocked", "blocked_pack", "blocked_non_copyable", "incompatible"):
        return "abort"
    return "skip"


def entry_row_to_plan_item(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Map design/admin/integration entry rows to unified plan item rows."""
    name = (
        entry.get("name")
        or entry.get("target_name")
        or entry.get("source_name")
        or entry.get("lookup")
        or entry.get("integration_id")
        or entry.get("playbook_name")
        or entry.get("source_id")
        or "?"
    )
    action = str(entry.get("action") or "skip")
    if action == "missing":
        action = "skip"
    elif action == "blocked_pack":
        action = "blocked"
    elif action == "incompatible":
        action = "blocked"
    item: dict[str, Any] = {"name": str(name), "action": action}
    if entry.get("reason"):
        item["reason"] = str(entry["reason"])
    if entry.get("proposed_name"):
        item["proposed_name"] = entry["proposed_name"]
    if entry.get("kind"):
        item["kind"] = entry["kind"]
    return item


def items_from_legacy_plan(legacy: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_items = list(legacy.get("items") or [])
    if raw_items:
        return raw_items
    flat = list(legacy.get("flat_items") or [])
    if flat:
        return [entry_row_to_plan_item(row) for row in flat]
    entries = list(legacy.get("entries") or [])
    return [entry_row_to_plan_item(row) for row in entries]


def wrap_legacy_preview_plan(
    legacy: dict[str, Any],
    *,
    operation: str,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    copy_mode: Optional[str] = None,
    rename_suffix: str = "",
    extra_warnings: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Attach plan_version to previews that only expose entries or legacy counts."""
    mode = parse_copy_mode(
        overwrite=overwrite,
        stop_on_conflict=stop_on_conflict,
        copy_mode=copy_mode,
    )
    items = items_from_legacy_plan(legacy)
    conflicts = list(legacy.get("conflicts") or [])
    if not conflicts:
        conflicts = [
            row
            for row in items
            if str(row.get("action") or "") in ("conflict", "blocked", "blocked_pack", "blocked_non_copyable")
        ]
    would_abort = legacy.get("would_abort")
    if would_abort is None:
        would_abort = bool(legacy.get("has_conflicts")) and stop_on_conflict
    would_abort = bool(would_abort) or plan_would_abort(
        mode=mode,
        stop_on_conflict=stop_on_conflict,
        conflicts=conflicts,
    )
    body = {
        **legacy,
        "items": items,
        "conflicts": conflicts,
        "would_abort": bool(would_abort),
        "overwrite": overwrite,
        "stop_on_conflict": stop_on_conflict,
    }
    return wrap_copy_plan(
        body,
        operation=operation,
        mode=mode,
        rename_suffix=rename_suffix,
        extra_warnings=extra_warnings,
    )


def build_plan_summary(items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    create = sum(1 for i in items if _action_to_summary_action(str(i.get("action") or "")) == "create")
    update = sum(1 for i in items if str(i.get("action") or "") == "update")
    skip = sum(1 for i in items if str(i.get("action") or "") == "skip")
    abort = sum(1 for i in items if str(i.get("action") or "") == "conflict")
    return {
        "total": len(items),
        "create": create,
        "update": update,
        "skip": skip,
        "abort": abort,
    }


def _collect_risks(
    *,
    mode: CopyMode,
    summary: dict[str, Any],
    operation: str,
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    if mode == "overwrite" and summary.get("update", 0) > 0:
        n = summary["update"]
        risks.append(
            {
                "code": "OVERWRITE",
                "severity": "high",
                "message": f"{n} item(s) will replace existing content on the target tenant.",
            },
        )
    if mode == "copy_as_new" and summary.get("create", 0) > 0:
        risks.append(
            {
                "code": "COPY_AS_NEW",
                "severity": "medium",
                "message": (
                    f"{summary['create']} new object(s) will be created under renamed titles; "
                    "references in copied playbooks must be rebound where applicable."
                ),
            },
        )
    if summary.get("abort", 0) > 0:
        risks.append(
            {
                "code": "PLAN_ABORT",
                "severity": "high",
                "message": f"{summary['abort']} item(s) block this plan until resolved.",
            },
        )
    if operation.startswith("playbooks.copy_shallow"):
        risks.append(
            {
                "code": "SHALLOW_BIND",
                "severity": "medium",
                "message": "Playbook documents only; scripts and sub-playbooks must already exist on target.",
            },
        )
    return risks


def _mode_description(mode: CopyMode, *, rename_suffix: str = "") -> str:
    if mode == "overwrite":
        return "Overwrite: existing target objects with the same name will be updated."
    if mode == "copy_as_new":
        suf = rename_suffix or "_copy"
        return (
            f"Copy as new: conflicting names receive suffix {suf!r} (or per-item map); "
            "all resulting names are checked for collisions on target."
        )
    return "Skip existing: objects that already exist on target (same name) will not be uploaded."


def build_copy_steps(
    *,
    operation: str,
    mode: CopyMode,
    item_count: int,
    extra_phases: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [
        {"phase": 1, "label": "Validate copy mode and target name collisions", "automated": True},
    ]
    phase = 2
    for extra in extra_phases or []:
        steps.append({**extra, "phase": phase})
        phase += 1
    if "shallow" in operation:
        steps.append(
            {
                "phase": phase,
                "label": f"Upload {item_count} playbook document(s) (shallow; bind to target cache)",
                "automated": True,
            },
        )
    else:
        steps.append(
            {
                "phase": phase,
                "label": f"Upload or update {item_count} item(s) on target",
                "automated": True,
            },
        )
    steps.append({"phase": phase + 1, "label": "Refresh target cache (after upload)", "automated": True})
    return steps


def wrap_copy_plan(
    legacy: dict[str, Any],
    *,
    operation: str,
    mode: CopyMode,
    rename_suffix: str = "",
    extra_steps: Optional[list[dict[str, Any]]] = None,
    extra_warnings: Optional[list[dict[str, Any]]] = None,
    binding_table: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Attach plan_version envelope; keep legacy keys for CLI and older UI."""
    items = list(legacy.get("items") or [])
    summary = build_plan_summary(items)
    would_abort = legacy.get("would_abort")
    if would_abort is None:
        conflicts = list(legacy.get("conflicts") or [])
        would_abort = plan_would_abort(
            mode=mode,
            stop_on_conflict=bool(legacy.get("stop_on_conflict")),
            conflicts=conflicts,
        )

    warnings: list[dict[str, Any]] = list(extra_warnings or [])
    for w in legacy.get("warnings") or []:
        if isinstance(w, dict):
            warnings.append(w)
        elif isinstance(w, str):
            warnings.append({"code": "LEGACY", "message": w})

    skip_names = [i.get("name") for i in items if i.get("action") == "skip"]
    if skip_names and mode == "skip":
        warnings.append(
            {
                "code": "WILL_SKIP",
                "message": f"{len(skip_names)} item(s) already on target will be skipped: "
                + ", ".join(str(n) for n in skip_names[:8])
                + ("…" if len(skip_names) > 8 else ""),
            },
        )

    risks = _collect_risks(mode=mode, summary=summary, operation=operation)
    steps = build_copy_steps(
        operation=operation,
        mode=mode,
        item_count=len(items),
        extra_phases=extra_steps,
    )

    out = dict(legacy)
    out.update(
        {
            "plan_version": PLAN_VERSION,
            "operation": operation,
            "copy_mode": mode,
            "mode_description": _mode_description(mode, rename_suffix=rename_suffix),
            "rename_suffix": rename_suffix,
            "summary": summary,
            "steps": steps,
            "risks": risks,
            "warnings": warnings,
            "would_abort": bool(would_abort),
            "abort_reason": legacy.get("abort_reason")
            or (
                "Plan blocked by name conflicts or invalid rename targets."
                if would_abort
                else None
            ),
        },
    )
    if binding_table is not None:
        out["binding_table"] = binding_table
    return out


def _normalize_delete_action(action: str) -> str:
    if action in ("delete",):
        return "delete"
    if action in ("blocked", "blocked_system", "blocked_pack", "blocked_non_copyable"):
        return "blocked"
    if action in ("not_found", "missing", "skip"):
        return "skip"
    return action


def delete_entry_to_plan_item(entry: Mapping[str, Any]) -> dict[str, Any]:
    name = (
        entry.get("name")
        or entry.get("display")
        or entry.get("list_id")
        or entry.get("playbook_id")
        or entry.get("script_id")
        or entry.get("integration_id")
        or entry.get("item_id")
        or entry.get("id")
        or "?"
    )
    if "action" in entry:
        action = _normalize_delete_action(str(entry.get("action") or "skip"))
    elif "deletable" in entry:
        action = "delete" if entry.get("deletable") else "blocked"
    else:
        action = "skip"
    item: dict[str, Any] = {"name": str(name), "action": action}
    if entry.get("reason"):
        item["reason"] = str(entry["reason"])
    if entry.get("instance_count"):
        item["instance_count"] = entry["instance_count"]
    return item


def build_delete_summary(items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    delete = sum(1 for i in items if i.get("action") == "delete")
    blocked = sum(1 for i in items if i.get("action") == "blocked")
    skip = sum(1 for i in items if i.get("action") == "skip")
    return {
        "total": len(items),
        "delete": delete,
        "blocked": blocked,
        "skip": skip,
        "abort": blocked,
    }


def wrap_delete_plan(
    legacy: dict[str, Any],
    *,
    operation: str,
    extra_warnings: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Attach plan_version to delete preview responses."""
    items: list[dict[str, Any]] = []
    for row in legacy.get("items") or legacy.get("entries") or []:
        items.append(delete_entry_to_plan_item(row))

    summary = build_delete_summary(items)
    would_delete = legacy.get("would_delete")
    if would_delete is None:
        would_delete = summary["delete"] > 0
    would_abort = not would_delete

    warnings: list[dict[str, Any]] = list(extra_warnings or [])
    for w in legacy.get("warnings") or []:
        if isinstance(w, dict):
            inst = w.get("instance_count")
            if inst:
                warnings.append(
                    {
                        "code": "DELETE_WITH_INSTANCES",
                        "message": (
                            f"Integration {w.get('name') or w.get('integration_id')!r} has "
                            f"{inst} instance(s) on tenant — delete removes definition only."
                        ),
                    },
                )
            else:
                warnings.append(w)
        elif isinstance(w, str):
            warnings.append({"code": "LEGACY", "message": w})

    risks: list[dict[str, Any]] = []
    if summary["delete"] > 0:
        risks.append(
            {
                "code": "PERMANENT_DELETE",
                "severity": "high",
                "message": f"{summary['delete']} object(s) will be permanently removed from the tenant.",
            },
        )
    if summary["blocked"] > 0:
        risks.append(
            {
                "code": "BLOCKED_ITEMS",
                "severity": "medium",
                "message": f"{summary['blocked']} item(s) cannot be deleted (system or policy).",
            },
        )
    if legacy.get("has_instance_warnings"):
        risks.append(
            {
                "code": "INTEGRATION_INSTANCES",
                "severity": "high",
                "message": "One or more integrations still have configured instances on the tenant.",
            },
        )

    out = dict(legacy)
    out.update(
        {
            "plan_version": PLAN_VERSION,
            "operation": operation,
            "profile": legacy.get("profile") or legacy.get("source_profile"),
            "items": items,
            "summary": summary,
            "counts": legacy.get("counts") or summary,
            "steps": [
                {"phase": 1, "label": "Validate delete permissions and system locks", "automated": True},
                {"phase": 2, "label": f"Delete {summary['delete']} object(s) on tenant", "automated": True},
                {"phase": 3, "label": "Refresh local cache", "automated": True},
            ],
            "risks": risks,
            "warnings": warnings or None,
            "would_abort": would_abort,
            "would_delete": bool(would_delete),
            "abort_reason": (
                "Nothing deletable in selection."
                if would_abort
                else None
            ),
            "mode_description": "Delete: selected objects are removed from the tenant when permitted.",
        },
    )
    return out


def wrap_refactor_plan(legacy: dict[str, Any]) -> dict[str, Any]:
    """Attach plan_version to playbook refactor preview."""
    extractions = list(legacy.get("extractions") or [])
    items: list[dict[str, Any]] = []
    for row in extractions:
        label = row.get("subplaybook_name") or row.get("task_label") or row.get("task_id") or "?"
        kind = str(row.get("kind") or "extract")
        items.append({"name": str(label), "action": "create", "kind": kind})
    parent_copy = legacy.get("parent_copy_name")
    if parent_copy:
        items.append({"name": str(parent_copy), "action": "create", "kind": "parent_copy"})

    existing = list(legacy.get("existing_targets") or [])
    summary = build_plan_summary(items)
    ok = bool(legacy.get("ok", True))
    would_abort = not ok

    warnings: list[dict[str, Any]] = []
    for reason in legacy.get("reasons") or []:
        warnings.append({"code": "REFACTOR_VALIDATION", "message": str(reason)})

    risks: list[dict[str, Any]] = [
        {
            "code": "LIVE_TENANT_UPLOAD",
            "severity": "high",
            "message": "Refactor uploads new sub-playbooks and a parent copy; the source playbook is never modified.",
        },
    ]
    if existing:
        risks.append(
            {
                "code": "OVERWRITE",
                "severity": "high",
                "message": (
                    f"{len(existing)} existing playbook(s) on tenant match planned output names — "
                    "enable overwrite and confirm to replace in place."
                ),
            },
        )

    profile = str(legacy.get("profile") or "")
    source_pb = legacy.get("source_playbook") or {}
    return {
        **legacy,
        "plan_version": PLAN_VERSION,
        "operation": "playbooks.refactor",
        "source_profile": profile,
        "target_profile": profile,
        "items": items,
        "summary": summary,
        "steps": [
            {"phase": 1, "label": "Validate extract graph (leaf/cluster checks)", "automated": True},
            {"phase": 2, "label": "Upload sub-playbook(s) in parallel", "automated": True},
            {"phase": 3, "label": "Post-task updates + descriptions on parent copy", "automated": True},
        ],
        "risks": risks,
        "warnings": warnings or None,
        "would_abort": would_abort,
        "abort_reason": (
            "; ".join(str(r) for r in (legacy.get("reasons") or [])[:3]) or "Refactor validation failed."
        )
        if would_abort
        else None,
        "mode_description": (
            f"Refactor {source_pb.get('name') or 'playbook'}: "
            f"{len(extractions)} extraction(s) + parent copy {parent_copy!r}."
        ),
        "existing_targets": existing,
        "overwrite_required": bool(legacy.get("overwrite_required")),
    }
