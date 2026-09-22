"""Inspect playbook tasks: titles, successor counts, potential-root status."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Mapping, Optional, Sequence

from .graph import PotentialRootResult, check_potential_root, descendant_ids, total_successors
from .keys import JsonDict, playbook_tasks, successor_ids, task_name, task_type


_TRUE = {"yes", "true", "1", "ok"}
_FALSE = {"no", "false", "0"}
_KEY_ALIASES = {
    "title": "name",
    "task": "id",
    "task_id": "id",
    "potential-root": "root",
    "potential_root": "root",
    "successor_count": "successors",
    "total_successors": "successors",
}


def task_sort_key(task_id: str) -> tuple:
    try:
        return (0, int(task_id), task_id)
    except ValueError:
        return (1, 0, task_id)


def resolve_task_ref(playbook: Mapping[str, object], ref: str) -> str:
    """Resolve a tasks-map key or a unique task name to a task id."""
    key = str(ref)
    tasks = playbook_tasks(playbook)
    if key in tasks:
        return key
    matches = [tid for tid, node in tasks.items() if task_name(node) == key]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise KeyError(f"No task with id or name {key!r}")
    raise KeyError(f"Multiple tasks named {key!r}: {', '.join(matches)}")


def parse_bool_flag(value: str) -> bool:
    token = value.strip().lower()
    if token in _TRUE:
        return True
    if token in _FALSE:
        return False
    raise ValueError(f"Expected yes/no (or true/false), got {value!r}")


@dataclass
class TaskInspection:
    task_id: str
    exists: bool
    name: str
    type: str
    direct_successor_ids: List[str]
    successor_ids: List[str]
    successor_count: int
    potential_root: bool
    potential_root_reasons: List[str]
    descendant_ids: List[str]

    def to_dict(self) -> JsonDict:
        return {
            "task_id": self.task_id,
            "exists": self.exists,
            "name": self.name,
            "type": self.type,
            "direct_successor_ids": list(self.direct_successor_ids),
            "successor_ids": list(self.successor_ids),
            "successor_count": self.successor_count,
            "potential_root": self.potential_root,
            "potential_root_reasons": list(self.potential_root_reasons),
            "descendant_ids": list(self.descendant_ids),
        }


@dataclass
class ExpectSpec:
    task_id: str
    name: Optional[str] = None
    successors: Optional[int] = None
    potential_root: Optional[bool] = None

    def to_dict(self) -> JsonDict:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "successors": self.successors,
            "potential_root": self.potential_root,
        }


@dataclass
class ExpectResult:
    spec: ExpectSpec
    ok: bool
    mismatches: List[str] = field(default_factory=list)
    inspection: Optional[TaskInspection] = None

    def to_dict(self) -> JsonDict:
        return {
            "ok": self.ok,
            "spec": self.spec.to_dict(),
            "mismatches": list(self.mismatches),
            "inspection": None if self.inspection is None else self.inspection.to_dict(),
        }


def parse_expect_spec(spec: str) -> ExpectSpec:
    """Parse `7,name=Print Key_In_Main,successors=2,root=yes`."""
    text = spec.strip()
    if not text:
        raise ValueError("empty --check spec")
    parts = [part.strip() for part in text.split(",") if part.strip()]
    data: dict[str, str] = {}
    if parts and "=" not in parts[0]:
        data["id"] = parts[0]
        parts = parts[1:]
    for part in parts:
        if "=" not in part:
            raise ValueError(f"Expected key=value in {spec!r}, got {part!r}")
        raw_key, raw_value = part.split("=", 1)
        key = _KEY_ALIASES.get(raw_key.strip().lower(), raw_key.strip().lower())
        data[key] = raw_value.strip()
    task_id = data.get("id")
    if not task_id:
        raise ValueError(f"Missing task id in --check spec {spec!r}")
    successors: Optional[int] = None
    if "successors" in data:
        successors = int(data["successors"])
    root: Optional[bool] = None
    if "root" in data:
        root = parse_bool_flag(data["root"])
    return ExpectSpec(
        task_id=str(task_id),
        name=data.get("name"),
        successors=successors,
        potential_root=root,
    )


def inspect_task(playbook: Mapping[str, object], task_id: str) -> TaskInspection:
    tid = str(task_id)
    tasks = playbook_tasks(playbook)
    node = tasks.get(tid)
    check: PotentialRootResult = check_potential_root(playbook, tid)
    if node is None:
        return TaskInspection(
            task_id=tid,
            exists=False,
            name="",
            type="",
            direct_successor_ids=[],
            successor_ids=[],
            successor_count=0,
            potential_root=False,
            potential_root_reasons=list(check.reasons),
            descendant_ids=[],
        )
    successors = total_successors(playbook, tid)
    return TaskInspection(
        task_id=tid,
        exists=True,
        name=task_name(node),
        type=task_type(node),
        direct_successor_ids=list(successor_ids(node)),
        successor_ids=successors,
        successor_count=len(successors),
        potential_root=check.ok,
        potential_root_reasons=list(check.reasons),
        descendant_ids=list(descendant_ids(playbook, tid)),
    )


def inspect_playbook(
    playbook: Mapping[str, object],
    task_ids: Optional[Iterable[str]] = None,
) -> List[TaskInspection]:
    tasks = playbook_tasks(playbook)
    if task_ids is None:
        wanted = list(tasks.keys())
    else:
        wanted = [str(tid) for tid in task_ids]
    wanted = list(dict.fromkeys(wanted))
    wanted.sort(key=task_sort_key)
    return [inspect_task(playbook, tid) for tid in wanted]


def evaluate_expect(playbook: Mapping[str, object], spec: ExpectSpec) -> ExpectResult:
    inspection = inspect_task(playbook, spec.task_id)
    mismatches: List[str] = []
    if spec.name is not None and inspection.name != spec.name:
        mismatches.append(f"name: expected {spec.name!r}, got {inspection.name!r}")
    if spec.successors is not None and inspection.successor_count != spec.successors:
        mismatches.append(
            f"successors: expected {spec.successors}, got {inspection.successor_count}"
        )
    if spec.potential_root is not None and inspection.potential_root != spec.potential_root:
        wanted = "yes" if spec.potential_root else "no"
        got = "yes" if inspection.potential_root else "no"
        mismatches.append(f"potential_root: expected {wanted}, got {got}")
        mismatches.extend(inspection.potential_root_reasons)
    if not inspection.exists:
        mismatches.append(f"task {spec.task_id!r} does not exist")
    return ExpectResult(
        spec=spec,
        ok=not mismatches,
        mismatches=mismatches,
        inspection=inspection,
    )


def evaluate_expects(
    playbook: Mapping[str, object],
    specs: Sequence[ExpectSpec],
) -> List[ExpectResult]:
    return [evaluate_expect(playbook, spec) for spec in specs]


def format_inspect_text(
    playbook: Mapping[str, object],
    reports: Sequence[TaskInspection],
    expects: Optional[Sequence[ExpectResult]] = None,
) -> str:
    lines = [
        f"Playbook: {playbook.get('name')} ({playbook.get('id')})",
        f"Tasks shown: {len(reports)}",
        "",
        f"{'ID':<8} {'TYPE':<12} {'SUCC':>4} {'ROOT':<5}  NAME",
        f"{'-'*8} {'-'*12} {'-'*4} {'-'*5}  {'-'*40}",
    ]
    for report in reports:
        root = "yes" if report.potential_root else "no"
        if not report.exists:
            root = "—"
        lines.append(
            f"{report.task_id:<8} {report.type:<12} {report.successor_count:>4} {root:<5}  {report.name}"
        )
        if report.potential_root_reasons and not report.potential_root:
            for reason in report.potential_root_reasons:
                lines.append(f"{'':8}  {reason}")
    if expects:
        lines.append("")
        lines.append("Checks:")
        for result in expects:
            status = "PASS" if result.ok else "FAIL"
            bits = [f"task {result.spec.task_id}"]
            if result.spec.name is not None:
                bits.append(f"name={result.spec.name!r}")
            if result.spec.successors is not None:
                bits.append(f"successors={result.spec.successors}")
            if result.spec.potential_root is not None:
                bits.append("root=yes" if result.spec.potential_root else "root=no")
            lines.append(f"  {status}  " + " ".join(bits))
            for mismatch in result.mismatches:
                lines.append(f"         {mismatch}")
    return "\n".join(lines)
