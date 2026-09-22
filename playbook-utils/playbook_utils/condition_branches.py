"""Analyze conditional task branches and trace upstream variable assignments."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from .cache import PlaybookCache
from .graph import incoming_edges
from .inspect import resolve_task_ref, task_sort_key
from .keys import (
    JsonDict,
    get_field,
    inner_task,
    next_tasks_map,
    playbook_tasks,
    start_task_id,
    successor_ids,
    task_name,
    task_type,
)
from .playbook_tree import format_nesting_path, resolve_sub_playbook
from .task_output_search import script_binding_candidates, script_command_name
from .task_summary import compact_task_summary, format_compact_task_summary


@dataclass(frozen=True)
class ContextRef:
    expression: str
    is_context: bool
    source: str  # left | right

    def normalized_keys(self) -> Set[str]:
        """Return match keys for assignment lookup."""
        expr = self.expression.strip()
        keys = {expr.casefold()}
        if expr.casefold().startswith("incident."):
            keys.add(expr.split(".", 1)[1].casefold())
        if expr.casefold().startswith("issue."):
            keys.add(expr.split(".", 1)[1].casefold())
        if expr.casefold().startswith("inputs."):
            keys.add(expr.split(".", 1)[1].casefold())
            keys.add(expr.casefold())
        return keys


@dataclass
class ConditionClause:
    operator: str
    left: Optional[ContextRef]
    right: Optional[ContextRef]

    def summary(self) -> str:
        left = self.left.expression if self.left else "?"
        right = self.right.expression if self.right else "?"
        return f"{left} {self.operator} {right}"


@dataclass
class BranchSpec:
    label: str
    successor_task_ids: List[str]
    clauses: List[ConditionClause]
    variables: List[ContextRef] = field(default_factory=list)
    expected_values: List[str] = field(default_factory=list)

    def condition_summary(self) -> str:
        if not self.clauses:
            return "(default / no explicit condition)"
        return " OR ".join(clause.summary() for clause in self.clauses)


@dataclass
class VariableAssignment:
    variable: str
    task_id: str
    task_name: str
    task_type: str
    script_binding: str
    containing_playbook_id: str
    containing_playbook_name: str
    nesting_path: List[str]
    assignment_kind: str
    assigned_value: Optional[str]
    detail: str
    fallback: bool = False
    task_summary: JsonDict = field(default_factory=dict)

    @property
    def nesting_path_text(self) -> str:
        return format_nesting_path(self.nesting_path)

    def to_dict(self) -> JsonDict:
        payload = {
            "variable": self.variable,
            "task_id": self.task_id,
            "task_name": self.task_name,
            "task_type": self.task_type,
            "script_binding": self.script_binding,
            "containing_playbook_id": self.containing_playbook_id,
            "containing_playbook_name": self.containing_playbook_name,
            "nesting_path": list(self.nesting_path),
            "nesting_path_text": self.nesting_path_text,
            "assignment_kind": self.assignment_kind,
            "assigned_value": self.assigned_value,
            "detail": self.detail,
            "fallback": self.fallback,
        }
        if self.task_summary:
            payload["task_summary"] = dict(self.task_summary)
        return payload


@dataclass
class BranchAnalysis:
    label: str
    successor_task_ids: List[str]
    condition_summary: str
    variables: List[str]
    assignments: List[VariableAssignment]

    def to_dict(self) -> JsonDict:
        return {
            "label": self.label,
            "successor_task_ids": list(self.successor_task_ids),
            "condition_summary": self.condition_summary,
            "variables": list(self.variables),
            "assignments": [item.to_dict() for item in self.assignments],
        }


@dataclass
class ConditionBranchReport:
    root_playbook_id: str
    root_playbook_name: str
    condition_task_id: str
    condition_task_name: str
    condition_nesting_path: List[str]
    condition_task_summary: JsonDict
    branches: List[BranchAnalysis]

    def to_dict(self) -> JsonDict:
        return {
            "root_playbook_id": self.root_playbook_id,
            "root_playbook_name": self.root_playbook_name,
            "condition_task_id": self.condition_task_id,
            "condition_task_name": self.condition_task_name,
            "condition_nesting_path": list(self.condition_nesting_path),
            "condition_nesting_path_text": format_nesting_path(self.condition_nesting_path),
            "condition_task_summary": dict(self.condition_task_summary),
            "branches": [branch.to_dict() for branch in self.branches],
        }


@dataclass(frozen=True)
class _Frame:
    playbook: Mapping[str, object]
    task_id: str
    path: Tuple[str, ...]
    depth: int


def _value_ref(value_side: Mapping[str, object], *, source: str) -> Optional[ContextRef]:
    if not isinstance(value_side, Mapping):
        return None
    value = value_side.get("value")
    if not isinstance(value, Mapping):
        return None
    is_context = bool(value_side.get("isContext"))
    if "simple" in value and value.get("simple") is not None:
        return ContextRef(str(value.get("simple")), is_context, source)
    complex_value = value.get("complex")
    if isinstance(complex_value, Mapping):
        parts = [str(complex_value.get("root") or "")]
        accessor = complex_value.get("accessor")
        if accessor:
            parts.append(str(accessor))
        expression = ".".join(part for part in parts if part)
        return ContextRef(expression, is_context, source)
    return None


def _parse_clause(raw: Mapping[str, object]) -> ConditionClause:
    left = _value_ref(raw.get("left") or {}, source="left") if isinstance(raw.get("left"), Mapping) else None
    right = _value_ref(raw.get("right") or {}, source="right") if isinstance(raw.get("right"), Mapping) else None
    return ConditionClause(
        operator=str(raw.get("operator") or ""),
        left=left,
        right=right,
    )


def extract_branch_specs(node: Mapping[str, object]) -> List[BranchSpec]:
    """Parse a condition task into branch labels, clauses, and successor ids."""
    if task_type(node) != "condition":
        raise ValueError(f"Task {task_name(node)!r} is type {task_type(node)!r}, not condition")

    next_tasks = next_tasks_map(node)
    specs_by_label: dict[str, BranchSpec] = {}

    raw_conditions = get_field(node, "conditions") or []
    if isinstance(raw_conditions, list):
        for entry in raw_conditions:
            if not isinstance(entry, Mapping):
                continue
            label = str(entry.get("label") or "")
            clauses: List[ConditionClause] = []
            groups = entry.get("condition") or []
            if isinstance(groups, list):
                for group in groups:
                    if not isinstance(group, list):
                        continue
                    for raw_clause in group:
                        if isinstance(raw_clause, Mapping):
                            clauses.append(_parse_clause(raw_clause))
            variables = _branch_variables(clauses)
            expected = _branch_expected_values(clauses)
            specs_by_label[label] = BranchSpec(
                label=label,
                successor_task_ids=list(next_tasks.get(label) or []),
                clauses=clauses,
                variables=variables,
                expected_values=expected,
            )

    for label, successors in sorted(next_tasks.items()):
        if label in specs_by_label:
            if not specs_by_label[label].successor_task_ids:
                specs_by_label[label].successor_task_ids = list(successors)
            continue
        specs_by_label[label] = BranchSpec(
            label=str(label),
            successor_task_ids=list(successors),
            clauses=[],
            variables=[],
            expected_values=[],
        )

    return [specs_by_label[label] for label in sorted(specs_by_label.keys(), key=str)]


def _branch_variables(clauses: Sequence[ConditionClause]) -> List[ContextRef]:
    seen: Set[str] = set()
    variables: List[ContextRef] = []
    for clause in clauses:
        for ref in (clause.left, clause.right):
            if ref is None or not ref.is_context:
                continue
            token = ref.expression.casefold()
            if token in seen:
                continue
            seen.add(token)
            variables.append(ref)
    return variables


def _branch_expected_values(clauses: Sequence[ConditionClause]) -> List[str]:
    values: List[str] = []
    for clause in clauses:
        if clause.operator.casefold() not in {"isequalstring", "is equal string"}:
            continue
        if clause.left and clause.left.is_context and clause.right and not clause.right.is_context:
            values.append(clause.right.expression)
    return values


def _simple_value(arg: object) -> Optional[str]:
    if not isinstance(arg, Mapping):
        return None
    simple = arg.get("simple")
    if simple is not None:
        return str(simple)
    complex_value = arg.get("complex")
    if isinstance(complex_value, Mapping):
        return json.dumps(complex_value, sort_keys=True, default=str)
    return None


def _script_binding(node: Mapping[str, object]) -> str:
    inner = inner_task(node)
    if not inner:
        return ""
    candidates = script_binding_candidates(inner)
    return candidates[0] if candidates else ""


def _assignment_matches_variable(variable_keys: Set[str], assigned_key: str) -> bool:
    return assigned_key.casefold() in variable_keys


def _assignments_from_task(
    playbook: Mapping[str, object],
    path: Sequence[str],
    task_id: str,
    node: Mapping[str, object],
    variable_keys: Set[str],
) -> List[VariableAssignment]:
    playbook_id = str(playbook.get("id") or "")
    playbook_name = str(playbook.get("name") or playbook_id)
    binding = _script_binding(node)
    command = script_command_name(binding).casefold() if binding else ""
    matches: List[VariableAssignment] = []

    script_args = get_field(node, "scriptArguments")
    if isinstance(script_args, Mapping):
        if command == "set":
            key_val = _simple_value(script_args.get("key"))
            value_val = _simple_value(script_args.get("value"))
            if key_val and _assignment_matches_variable(variable_keys, key_val):
                matches.append(
                    VariableAssignment(
                        variable=key_val,
                        task_id=task_id,
                        task_name=task_name(node),
                        task_type=task_type(node),
                        script_binding=binding,
                        containing_playbook_id=playbook_id,
                        containing_playbook_name=playbook_name,
                        nesting_path=list(path),
                        assignment_kind="set",
                        assigned_value=value_val,
                        detail=f"Set context key {key_val!r}",
                    )
                )
        elif command == "setissue":
            for field_name, arg in script_args.items():
                assigned_value = _simple_value(arg)
                if _assignment_matches_variable(variable_keys, str(field_name)):
                    matches.append(
                        VariableAssignment(
                            variable=str(field_name),
                            task_id=task_id,
                            task_name=task_name(node),
                            task_type=task_type(node),
                            script_binding=binding,
                            containing_playbook_id=playbook_id,
                            containing_playbook_name=playbook_name,
                            nesting_path=list(path),
                            assignment_kind="setIssue",
                            assigned_value=assigned_value,
                            detail=f"setIssue field {field_name!r}",
                        )
                    )
        else:
            for field_name, arg in script_args.items():
                assigned_value = _simple_value(arg)
                if _assignment_matches_variable(variable_keys, str(field_name)):
                    matches.append(
                        VariableAssignment(
                            variable=str(field_name),
                            task_id=task_id,
                            task_name=task_name(node),
                            task_type=task_type(node),
                            script_binding=binding,
                            containing_playbook_id=playbook_id,
                            containing_playbook_name=playbook_name,
                            nesting_path=list(path),
                            assignment_kind="scriptArguments",
                            assigned_value=assigned_value,
                            detail=f"{command or 'script'} argument {field_name!r}",
                        )
                    )

    if task_type(node) == "playbook" and isinstance(script_args, Mapping):
        for field_name, arg in script_args.items():
            assigned_value = _simple_value(arg)
            for key in variable_keys:
                if key.startswith("inputs.") and key.split(".", 1)[1].casefold() == str(field_name).casefold():
                    matches.append(
                        VariableAssignment(
                            variable=f"inputs.{field_name}",
                            task_id=task_id,
                            task_name=task_name(node),
                            task_type=task_type(node),
                            script_binding=binding,
                            containing_playbook_id=playbook_id,
                            containing_playbook_name=playbook_name,
                            nesting_path=list(path),
                            assignment_kind="playbook_input",
                            assigned_value=assigned_value,
                            detail=f"Sub-playbook input {field_name!r}",
                        )
                    )
                elif key.casefold() == str(field_name).casefold():
                    matches.append(
                        VariableAssignment(
                            variable=str(field_name),
                            task_id=task_id,
                            task_name=task_name(node),
                            task_type=task_type(node),
                            script_binding=binding,
                            containing_playbook_id=playbook_id,
                            containing_playbook_name=playbook_name,
                            nesting_path=list(path),
                            assignment_kind="playbook_input",
                            assigned_value=assigned_value,
                            detail=f"Sub-playbook input {field_name!r}",
                        )
                    )
    return matches


def _forward_reachable(playbook: Mapping[str, object], start: str) -> List[str]:
    """Return task ids reachable from ``start`` via nextTasks (including start)."""
    tasks = playbook_tasks(playbook)
    if start not in tasks:
        return []
    seen: Set[str] = {start}
    queue: List[str] = [start]
    order: List[str] = []
    while queue:
        tid = queue.pop(0)
        order.append(tid)
        node = tasks.get(tid)
        if node is None:
            continue
        for succ in successor_ids(node):
            if succ not in seen:
                seen.add(succ)
                queue.append(succ)
    return order


def _collect_upstream_frames(
    playbook: Mapping[str, object],
    cache: PlaybookCache,
    task_id: str,
    path: Sequence[str],
) -> List[_Frame]:
    """Breadth-first upstream walk, expanding sub-playbook bodies on call predecessors."""
    frames: List[_Frame] = []
    queue: List[_Frame] = [_Frame(playbook, str(task_id), tuple(path), 0)]
    seen: Set[Tuple[str, str, Tuple[str, ...]]] = set()

    while queue:
        frame = queue.pop(0)
        key = (str(frame.playbook.get("id") or ""), frame.task_id, frame.path)
        if key in seen:
            continue
        seen.add(key)
        frames.append(frame)

        for edge in incoming_edges(frame.playbook, [frame.task_id]):
            pred_id = edge.source_id
            pred_node = playbook_tasks(frame.playbook).get(pred_id)
            if pred_node is not None and task_type(pred_node) == "playbook":
                sub = resolve_sub_playbook(cache, pred_node)
                if sub is not None:
                    sub_name = str(sub.get("name") or sub.get("id") or "")
                    sub_path = frame.path + (sub_name,)
                    sub_start = start_task_id(sub)
                    reachable = _forward_reachable(sub, sub_start)
                    for sub_tid in reversed(reachable):
                        if sub_tid == sub_start:
                            continue
                        queue.append(_Frame(sub, sub_tid, sub_path, frame.depth + 1))
            queue.append(_Frame(frame.playbook, pred_id, frame.path, frame.depth + 1))
    return frames


def _find_assignment(
    frames: Sequence[_Frame],
    variable: ContextRef,
    *,
    expected_value: Optional[str],
) -> Optional[VariableAssignment]:
    keys = variable.normalized_keys()
    candidates: List[VariableAssignment] = []
    for frame in frames:
        if frame.task_id == start_task_id(frame.playbook):
            continue
        node = playbook_tasks(frame.playbook).get(frame.task_id)
        if node is None:
            continue
        candidates.extend(
            _assignments_from_task(frame.playbook, frame.path, frame.task_id, node, keys)
        )
    if not candidates:
        return None
    if expected_value:
        for match in candidates:
            if match.assigned_value and match.assigned_value.casefold() == expected_value.casefold():
                return match
        if any(match.assignment_kind in {"setIssue", "playbook_input"} for match in candidates):
            return candidates[0]
        if all(match.assignment_kind == "set" for match in candidates):
            return None
    return candidates[0]


def _enrich_assignment_summary(
    cache: PlaybookCache,
    assignment: VariableAssignment,
) -> VariableAssignment:
    if assignment.fallback or not assignment.containing_playbook_id:
        return assignment
    try:
        playbook = cache.get(assignment.containing_playbook_id)
    except KeyError:
        return assignment
    node = playbook_tasks(playbook).get(assignment.task_id)
    if node is None:
        return assignment
    assignment.task_summary = compact_task_summary(node)
    return assignment


def _start_fallback(
    root_playbook: Mapping[str, object],
    variable: ContextRef,
) -> VariableAssignment:
    start = start_task_id(root_playbook)
    root_id = str(root_playbook.get("id") or "")
    root_name = str(root_playbook.get("name") or root_id)
    return VariableAssignment(
        variable=variable.expression,
        task_id=start,
        task_name="",
        task_type="start",
        script_binding="",
        containing_playbook_id=root_id,
        containing_playbook_name=root_name,
        nesting_path=[root_name],
        assignment_kind="start_fallback",
        assigned_value=None,
        detail="No upstream assignment found; value assumed from playbook/incident start context",
        fallback=True,
    )


def analyze_condition_branches(
    root_playbook: Mapping[str, object],
    cache: PlaybookCache,
    *,
    playbook: Mapping[str, object],
    task_id: str,
    nesting_path: Optional[Sequence[str]] = None,
) -> ConditionBranchReport:
    """Analyze branches for a condition task and trace upstream assignments."""
    tid = resolve_task_ref(playbook, str(task_id))
    node = playbook_tasks(playbook)[tid]
    if task_type(node) != "condition":
        raise ValueError(f"Task {tid} ({task_name(node)!r}) is not a condition task")

    root_id = str(root_playbook.get("id") or "")
    root_name = str(root_playbook.get("name") or root_id)
    current_path = list(nesting_path or [str(playbook.get("name") or root_name)])
    upstream_frames = _collect_upstream_frames(playbook, cache, tid, current_path)

    branch_results: List[BranchAnalysis] = []
    for spec in extract_branch_specs(node):
        assignments: List[VariableAssignment] = []
        for index, variable in enumerate(spec.variables):
            expected = spec.expected_values[index] if index < len(spec.expected_values) else (
                spec.expected_values[0] if len(spec.expected_values) == 1 else None
            )
            found = _find_assignment(upstream_frames, variable, expected_value=expected)
            assignment = found or _start_fallback(root_playbook, variable)
            assignments.append(_enrich_assignment_summary(cache, assignment))

        branch_results.append(
            BranchAnalysis(
                label=spec.label,
                successor_task_ids=list(spec.successor_task_ids),
                condition_summary=spec.condition_summary(),
                variables=[ref.expression for ref in spec.variables],
                assignments=assignments,
            )
        )

    return ConditionBranchReport(
        root_playbook_id=root_id,
        root_playbook_name=root_name,
        condition_task_id=tid,
        condition_task_name=task_name(node),
        condition_nesting_path=list(current_path),
        condition_task_summary=compact_task_summary(node),
        branches=branch_results,
    )


def locate_condition_task(
    root_playbook: Mapping[str, object],
    cache: PlaybookCache,
    task_ref: str,
) -> Tuple[Mapping[str, object], str, List[str]]:
    """Resolve a task ref in the root playbook tree."""
    root_name = str(root_playbook.get("name") or root_playbook.get("id") or "")

    def search(playbook: Mapping[str, object], path: List[str], chain: Set[str]) -> Optional[Tuple[Mapping[str, object], str, List[str]]]:
        try:
            tid = resolve_task_ref(playbook, task_ref)
            return playbook, tid, path
        except KeyError:
            pass
        playbook_id = str(playbook.get("id") or "")
        if playbook_id in chain:
            return None
        next_chain = set(chain)
        if playbook_id:
            next_chain.add(playbook_id)
        for _task_id, node in playbook_tasks(playbook).items():
            if task_type(node) != "playbook":
                continue
            sub = resolve_sub_playbook(cache, node)
            if sub is None:
                continue
            sub_name = str(sub.get("name") or sub.get("id") or "")
            hit = search(sub, path + [sub_name], next_chain)
            if hit is not None:
                return hit
        return None

    hit = search(root_playbook, [root_name], set())
    if hit is None:
        raise KeyError(f"Task {task_ref!r} not found in playbook tree rooted at {root_name!r}")
    return hit


def analyze_condition_branches_by_ref(
    root_playbook: Mapping[str, object],
    cache: PlaybookCache,
    task_ref: str,
) -> ConditionBranchReport:
    playbook, task_id, path = locate_condition_task(root_playbook, cache, task_ref)
    return analyze_condition_branches(
        root_playbook,
        cache,
        playbook=playbook,
        task_id=task_id,
        nesting_path=path,
    )


def format_condition_branch_report_agent(report: ConditionBranchReport) -> str:
    lines = [
        f"Playbook: {report.root_playbook_name} ({report.root_playbook_id})",
        format_compact_task_summary(
            report.condition_task_id,
            report.condition_task_summary,
            nesting_path=format_nesting_path(report.condition_nesting_path),
        ),
        f"Branches: {len(report.branches)}",
        "",
    ]
    for branch in report.branches:
        lines.append(f"## {branch.label}")
        lines.append(f"Successors: {', '.join(branch.successor_task_ids) or '—'}")
        lines.append(f"When: {branch.condition_summary}")
        if not branch.assignments:
            lines.append("Driver: (default branch — no condition variables)")
        for assignment in branch.assignments:
            if assignment.fallback:
                lines.append(
                    f"Driver: {assignment.variable} — **no upstream assignment in playbook tree** "
                    f"(start_fallback; may be dead branch or set outside playbook)"
                )
                continue
            value = f" = {assignment.assigned_value!r}" if assignment.assigned_value else ""
            lines.append(
                f"Driver: {assignment.variable}{value} via task {assignment.task_id} "
                f"{assignment.task_name!r} [{assignment.assignment_kind}]"
            )
            lines.append(f"  path: {assignment.nesting_path_text}")
            if assignment.task_summary:
                lines.append(
                    format_compact_task_summary(
                        assignment.task_id,
                        assignment.task_summary,
                        playbook_name=assignment.containing_playbook_name,
                    ).replace("\n", "\n  ")
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_condition_branch_report_text(report: ConditionBranchReport) -> str:
    lines = [
        f"Playbook: {report.root_playbook_name} ({report.root_playbook_id})",
        (
            "Condition: "
            f"{report.condition_task_name} (task {report.condition_task_id}) "
            f"at {format_nesting_path(report.condition_nesting_path)}"
        ),
        f"Branches: {len(report.branches)}",
        "",
    ]
    for branch in report.branches:
        lines.append(f"## {branch.label}")
        lines.append(f"Successors: {', '.join(branch.successor_task_ids) or '—'}")
        lines.append(f"Condition: {branch.condition_summary}")
        if branch.variables:
            lines.append(f"Variables: {', '.join(branch.variables)}")
        else:
            lines.append("Variables: (default branch)")
        for assignment in branch.assignments:
            prefix = "fallback" if assignment.fallback else assignment.assignment_kind
            value = f" = {assignment.assigned_value!r}" if assignment.assigned_value else ""
            lines.append(
                f"  - {assignment.variable}: task {assignment.task_id} "
                f"{assignment.task_name!r} [{prefix}]{value}"
            )
            lines.append(f"    {assignment.nesting_path_text}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
