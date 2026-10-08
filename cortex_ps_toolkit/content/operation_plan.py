"""Versioned operation plan envelope for copy preview endpoints."""

from __future__ import annotations

from typing import Any, Literal, Optional, Sequence

from .copy_modes import CopyMode, plan_would_abort

PLAN_VERSION = 1


def _action_to_summary_action(action: str) -> str:
    if action == "update":
        return "update"
    if action in ("copy", "copy_as_new"):
        return "create"
    if action == "skip":
        return "skip"
    if action == "conflict":
        return "abort"
    return "skip"


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
