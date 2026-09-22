"""Compact task summaries for agent review (search, branch trace, show-task)."""

from __future__ import annotations

from typing import List, Mapping, Optional, Sequence

from .keys import (
    JsonDict,
    get_field,
    inner_task,
    next_tasks_map,
    task_name,
    task_type,
)
from .task_output_search import script_binding_candidates, script_command_name


def _simple_arg(value: object, *, max_len: int = 120) -> Optional[str]:
    if not isinstance(value, Mapping):
        return None
    simple = value.get("simple")
    if simple is not None:
        text = str(simple)
        if len(text) > max_len:
            return text[: max_len - 3] + "..."
        return text
    complex_value = value.get("complex")
    if isinstance(complex_value, Mapping):
        root = str(complex_value.get("root") or "")
        accessor = complex_value.get("accessor")
        if accessor:
            return f"${{{root}.{accessor}}}"
        return f"${{{root}}}" if root else None
    return None


def _script_binding(node: Mapping[str, object]) -> str:
    inner = inner_task(node)
    if not inner:
        return ""
    candidates = script_binding_candidates(inner)
    return candidates[0] if candidates else ""


def _compact_arguments(node: Mapping[str, object], *, limit: int = 12) -> JsonDict:
    binding = _script_binding(node)
    command = script_command_name(binding).casefold() if binding else ""
    script_args = get_field(node, "scriptArguments")
    if not isinstance(script_args, Mapping):
        return {}

    out: JsonDict = {}
    if command == "set":
        key_val = _simple_arg(script_args.get("key"))
        value_val = _simple_arg(script_args.get("value"))
        if key_val:
            out["set_key"] = key_val
        if value_val is not None:
            out["set_value"] = value_val
        return out

    for index, (field_name, arg) in enumerate(sorted(script_args.items(), key=lambda item: str(item[0]))):
        if index >= limit:
            out["..."] = f"+{len(script_args) - limit} more"
            break
        rendered = _simple_arg(arg)
        if rendered is not None:
            out[str(field_name)] = rendered
    return out


def _compact_successors(node: Mapping[str, object]) -> JsonDict:
    mapping = next_tasks_map(node)
    return {str(label): list(successors) for label, successors in sorted(mapping.items(), key=lambda item: str(item[0]))}


def _compact_branches(node: Mapping[str, object]) -> List[JsonDict]:
    if task_type(node) != "condition":
        return []
    from .condition_branches import extract_branch_specs

    branches: List[JsonDict] = []
    for spec in extract_branch_specs(node):
        branches.append(
            {
                "label": spec.label,
                "condition": spec.condition_summary(),
                "variables": [ref.expression for ref in spec.variables],
                "expected_values": list(spec.expected_values),
                "successors": list(spec.successor_task_ids),
            }
        )
    return branches


def compact_task_summary(node: Mapping[str, object]) -> JsonDict:
    """Return a small, review-friendly snapshot of one playbook task node."""
    inner = inner_task(node)
    binding = _script_binding(node)
    summary: JsonDict = {
        "name": task_name(node),
        "type": task_type(node),
    }
    if binding:
        summary["script"] = binding
    if inner:
        playbook_id = inner.get("playbookId")
        playbook_name = inner.get("playbookName")
        if playbook_id or playbook_name:
            summary["playbook_ref"] = str(playbook_name or playbook_id)
    successors = _compact_successors(node)
    if successors:
        summary["successors"] = successors
    branches = _compact_branches(node)
    if branches:
        summary["branches"] = branches
    arguments = _compact_arguments(node)
    if arguments:
        summary["arguments"] = arguments
    return summary


def format_compact_task_summary(
    task_id: str,
    summary: Mapping[str, object],
    *,
    playbook_name: str = "",
    nesting_path: str = "",
) -> str:
    """Single-task text block for agent-facing CLI output."""
    lines = [f"Task {task_id}: {summary.get('name')} ({summary.get('type')})"]
    if playbook_name:
        lines[0] += f"  [{playbook_name}]"
    if nesting_path:
        lines.append(f"  path: {nesting_path}")
    if summary.get("script"):
        lines.append(f"  script: {summary['script']}")
    if summary.get("playbook_ref"):
        lines.append(f"  sub-playbook: {summary['playbook_ref']}")
    branches = summary.get("branches")
    if isinstance(branches, list):
        for branch in branches:
            if not isinstance(branch, Mapping):
                continue
            label = branch.get("label", "?")
            condition = branch.get("condition", "")
            succs = branch.get("successors") or []
            lines.append(f"  branch {label!r}: {condition} -> {', '.join(map(str, succs)) or '—'}")
    arguments = summary.get("arguments")
    if isinstance(arguments, Mapping) and arguments:
        parts = [f"{key}={value!r}" for key, value in arguments.items()]
        lines.append(f"  args: {', '.join(parts)}")
    successors = summary.get("successors")
    if isinstance(successors, Mapping) and successors and not branches:
        for label, succs in successors.items():
            lines.append(f"  next {label!r}: {', '.join(map(str, succs)) or '—'}")
    return "\n".join(lines)
