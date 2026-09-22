"""Read and update sub-playbook context sharing (separateContext) on playbook call tasks."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, MutableMapping, Optional, Sequence

from .keys import JsonDict, get_field, set_canonical, task_name
from .task_checks import check_playbook_task


class ContextSharing(str, Enum):
    """How a sub-playbook call shares incident context with its parent."""

    GLOBAL = "global"
    SUBPLAYBOOK = "subplaybook"


@dataclass(frozen=True)
class TaskContextState:
    task_id: str
    task_title: str
    separate_context: bool
    sharing: ContextSharing

    def to_dict(self) -> JsonDict:
        return {
            "task_id": self.task_id,
            "task_title": self.task_title,
            "separateContext": self.separate_context,
            "sharing": self.sharing.value,
        }


@dataclass
class TaskContextUpdate:
    task_id: str
    sharing: ContextSharing

    def to_dict(self) -> JsonDict:
        return {"task_id": self.task_id, "sharing": self.sharing.value}


def read_task_context_state(node: Mapping[str, object], task_id: str) -> TaskContextState:
    separate = get_field(node, "separateContext")
    separate_context = bool(separate) if isinstance(separate, bool) else False
    sharing = ContextSharing.SUBPLAYBOOK if separate_context else ContextSharing.GLOBAL
    return TaskContextState(
        task_id=str(task_id),
        task_title=task_name(node),
        separate_context=separate_context,
        sharing=sharing,
    )


def apply_task_context_update(node: MutableMapping[str, object], update: TaskContextUpdate) -> None:
    set_canonical(node, "separateContext", update.sharing is ContextSharing.SUBPLAYBOOK)


def update_affects_context_sharing(_update: TaskContextUpdate) -> bool:
    return True


def preflight_context_updates(
    playbook: Mapping[str, object],
    updates: Sequence[TaskContextUpdate],
) -> tuple[list[TaskContextUpdate], list[JsonDict]]:
    from .keys import playbook_tasks

    tasks = playbook_tasks(playbook)
    accepted: list[TaskContextUpdate] = []
    rejected: list[JsonDict] = []
    for update in updates:
        node = tasks.get(str(update.task_id))
        if not isinstance(node, dict):
            rejected.append({"task_id": update.task_id, "error": "task does not exist"})
            continue
        try:
            check_playbook_task(node, update.task_id)
        except ValueError as exc:
            rejected.append({"task_id": update.task_id, "error": str(exc)})
            continue
        accepted.append(update)
    return accepted, rejected


def apply_playbook_context_updates(
    playbook: Mapping[str, object],
    updates: Sequence[TaskContextUpdate],
) -> JsonDict:
    pb = copy.deepcopy(dict(playbook))
    tasks = pb.get("tasks")
    if not isinstance(tasks, dict):
        raise KeyError("playbook has no tasks map")

    for update in updates:
        node = tasks.get(str(update.task_id))
        if not isinstance(node, dict):
            raise KeyError(f"task {update.task_id!r} does not exist")
        check_playbook_task(node, update.task_id)
        apply_task_context_update(node, update)
    return pb


def validate_task_context_states(
    playbook: Mapping[str, object],
    expected: Mapping[str, TaskContextState],
) -> List[JsonDict]:
    tasks = playbook.get("tasks") or {}
    mismatches: List[JsonDict] = []
    for task_id, want in expected.items():
        node = tasks.get(str(task_id))
        if not isinstance(node, dict):
            mismatches.append({"task_id": task_id, "error": "task missing after upload"})
            continue
        got = read_task_context_state(node, task_id)
        if got.sharing != want.sharing:
            mismatches.append(
                {
                    "task_id": task_id,
                    "expected": want.to_dict(),
                    "actual": got.to_dict(),
                }
            )
    return mismatches


def parse_context_update_spec(spec: str) -> TaskContextUpdate:
    """Parse ``TASK:global|subplaybook`` update specs from the CLI."""
    if ":" not in spec:
        raise ValueError(f"context update spec must look like TASK:global (got {spec!r})")
    task_id, action = spec.split(":", 1)
    task_id = task_id.strip()
    action = action.strip().lower()
    if not task_id:
        raise ValueError(f"context update spec missing task id: {spec!r}")
    if action in {"global", "share", "shared", "incident"}:
        sharing = ContextSharing.GLOBAL
    elif action in {"subplaybook", "isolated", "separate"}:
        sharing = ContextSharing.SUBPLAYBOOK
    else:
        raise ValueError(
            f"unknown context action {action!r} in {spec!r}; use 'global' or 'subplaybook'"
        )
    return TaskContextUpdate(task_id=task_id, sharing=sharing)


def format_context_state_lines(states: Sequence[TaskContextState]) -> str:
    lines = ["Task context-sharing state:"]
    for state in states:
        lines.append(
            f"  {state.task_id} ({state.task_title!r}): "
            f"sharing={state.sharing.value}, separateContext={state.separate_context}"
        )
    return "\n".join(lines)
