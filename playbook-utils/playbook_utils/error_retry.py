"""Read and update On Error retry / error-handling settings on playbook script tasks."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence

from .keys import JsonDict, get_field, playbook_tasks, pop_field, set_canonical, task_name
from .task_checks import check_regular_script_task

RETRY_COUNT_KEY = "retry-count"
RETRY_INTERVAL_KEY = "retry-interval"


class ErrorHandling(str, Enum):
    """Playbook task error-handling modes observed on XSOAR tenants."""

    STOP = "stop"
    CONTINUE = "continue"
    ERROR_PATH = "errorPath"


@dataclass(frozen=True)
class RetryConfig:
    count: Optional[int]
    interval: Optional[int]

    def to_dict(self) -> JsonDict:
        return {"count": self.count, "interval": self.interval}


@dataclass(frozen=True)
class TaskErrorState:
    task_id: str
    task_title: str
    retry: RetryConfig
    error_handling: ErrorHandling
    continue_on_error: Optional[bool]
    continue_on_error_type: str
    has_error_path: bool

    def to_dict(self) -> JsonDict:
        return {
            "task_id": self.task_id,
            "task_title": self.task_title,
            "retry": self.retry.to_dict(),
            "error_handling": self.error_handling.value,
            "continueOnError": self.continue_on_error,
            "continueOnErrorType": self.continue_on_error_type,
            "has_error_path": self.has_error_path,
        }


@dataclass
class TaskErrorUpdate:
    task_id: str
    clear_retry: bool = False
    retry_count: Optional[int] = None
    retry_interval: Optional[int] = None
    error_handling: Optional[ErrorHandling] = None

    def to_dict(self) -> JsonDict:
        return {
            "task_id": self.task_id,
            "clear_retry": self.clear_retry,
            "retry_count": self.retry_count,
            "retry_interval": self.retry_interval,
            "error_handling": self.error_handling.value if self.error_handling else None,
        }


def _script_arguments(node: Mapping[str, Any]) -> MutableMapping[str, Any]:
    args = get_field(node, "scriptArguments")
    if isinstance(args, dict):
        return args
    return {}


def _simple_arg(args: Mapping[str, Any], key: str) -> Optional[str]:
    entry = args.get(key)
    if not isinstance(entry, dict):
        return None
    value = entry.get("simple")
    return str(value) if value is not None else None


def _parse_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    return int(value)


def _next_tasks(node: Mapping[str, Any]) -> Mapping[str, Any]:
    nxt = get_field(node, "nextTasks")
    return nxt if isinstance(nxt, dict) else {}


def read_task_error_state(node: Mapping[str, Any], task_id: str) -> TaskErrorState:
    """Return retry and error-handling state for one task node."""
    args = _script_arguments(node)
    continue_on_error = get_field(node, "continueOnError")
    continue_on_error_type = str(get_field(node, "continueOnErrorType") or "")
    has_error_path = "#error#" in _next_tasks(node)

    if continue_on_error_type == ErrorHandling.ERROR_PATH.value:
        handling = ErrorHandling.ERROR_PATH
    elif continue_on_error is True:
        handling = ErrorHandling.CONTINUE
    else:
        handling = ErrorHandling.STOP

    return TaskErrorState(
        task_id=str(task_id),
        task_title=task_name(node),
        retry=RetryConfig(
            count=_parse_int(_simple_arg(args, RETRY_COUNT_KEY)),
            interval=_parse_int(_simple_arg(args, RETRY_INTERVAL_KEY)),
        ),
        error_handling=handling,
        continue_on_error=continue_on_error if isinstance(continue_on_error, bool) else None,
        continue_on_error_type=continue_on_error_type,
        has_error_path=has_error_path,
    )


def _ensure_script_arguments(node: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    args = get_field(node, "scriptArguments")
    if not isinstance(args, dict):
        args = {}
        set_canonical(node, "scriptArguments", args)
    return args


def _set_simple_arg(args: MutableMapping[str, Any], key: str, value: str) -> None:
    args[key] = {"simple": value}


def _remove_arg(args: MutableMapping[str, Any], key: str) -> None:
    args.pop(key, None)
    lowered = key.lower()
    for existing in list(args.keys()):
        if str(existing).lower() == lowered:
            del args[existing]


def update_affects_error_settings(update: TaskErrorUpdate) -> bool:
    return bool(
        update.clear_retry
        or update.retry_count is not None
        or update.error_handling is not None
    )


def apply_task_error_update(node: MutableMapping[str, Any], update: TaskErrorUpdate) -> None:
    """Apply one task update in place."""
    if update_affects_error_settings(update):
        check_regular_script_task(node, update.task_id)
    args = _ensure_script_arguments(node)

    if update.clear_retry or (update.retry_count is not None and update.retry_count <= 0):
        _remove_arg(args, RETRY_COUNT_KEY)
        _remove_arg(args, RETRY_INTERVAL_KEY)
    elif update.retry_count is not None:
        if update.retry_interval is None:
            raise ValueError(
                f"task {update.task_id}: retry-interval is required when retry-count is set"
            )
        _set_simple_arg(args, RETRY_COUNT_KEY, str(update.retry_count))
        _set_simple_arg(args, RETRY_INTERVAL_KEY, str(update.retry_interval))

    if update.error_handling is not None:
        if update.error_handling is ErrorHandling.STOP:
            pop_field(node, "continueOnError")
            set_canonical(node, "continueOnErrorType", "")
        elif update.error_handling is ErrorHandling.CONTINUE:
            set_canonical(node, "continueOnError", True)
            set_canonical(node, "continueOnErrorType", "")
        elif update.error_handling is ErrorHandling.ERROR_PATH:
            set_canonical(node, "continueOnError", True)
            set_canonical(node, "continueOnErrorType", ErrorHandling.ERROR_PATH.value)

    if not args:
        pop_field(node, "scriptArguments")


def apply_playbook_error_updates(
    playbook: Mapping[str, Any],
    updates: Sequence[TaskErrorUpdate],
) -> JsonDict:
    """Return a deep copy of the playbook with task error updates applied."""
    pb = copy.deepcopy(dict(playbook))
    tasks = pb.get("tasks")
    if not isinstance(tasks, dict):
        raise KeyError("playbook has no tasks map")

    for update in updates:
        node = tasks.get(str(update.task_id))
        if not isinstance(node, dict):
            raise KeyError(f"task {update.task_id!r} does not exist")
        apply_task_error_update(node, update)
    return pb


def preflight_error_updates(
    playbook: Mapping[str, Any],
    updates: Sequence[TaskErrorUpdate],
) -> tuple[list[TaskErrorUpdate], list[JsonDict]]:
    """Split updates into accepted vs rejected based on task-type checks."""
    tasks = playbook_tasks(playbook)
    accepted: list[TaskErrorUpdate] = []
    rejected: list[JsonDict] = []
    for update in updates:
        if not update_affects_error_settings(update):
            rejected.append(
                {
                    "task_id": update.task_id,
                    "error": "update specifies no retry or error-handling change",
                }
            )
            continue
        node = tasks.get(str(update.task_id))
        if not isinstance(node, dict):
            rejected.append({"task_id": update.task_id, "error": "task does not exist"})
            continue
        try:
            check_regular_script_task(node, update.task_id)
        except ValueError as exc:
            rejected.append({"task_id": update.task_id, "error": str(exc)})
            continue
        accepted.append(update)
    return accepted, rejected


def validate_task_states(
    playbook: Mapping[str, Any],
    expected: Mapping[str, TaskErrorState],
) -> List[JsonDict]:
    """Compare task states; return a list of mismatch records (empty if all match)."""
    tasks = playbook.get("tasks") or {}
    mismatches: List[JsonDict] = []
    for task_id, want in expected.items():
        node = tasks.get(str(task_id))
        if not isinstance(node, dict):
            mismatches.append({"task_id": task_id, "error": "task missing after upload"})
            continue
        got = read_task_error_state(node, task_id)
        if got.retry != want.retry or got.error_handling != want.error_handling:
            mismatches.append(
                {
                    "task_id": task_id,
                    "expected": want.to_dict(),
                    "actual": got.to_dict(),
                }
            )
    return mismatches


def parse_update_spec(spec: str) -> TaskErrorUpdate:
    """Parse ``TASK:action[,action…]`` update specs from the CLI.

    Actions:
    - ``clear-retry`` — remove retry-count / retry-interval
    - ``stop-on-error`` / ``continue`` / ``error-path`` — error handling mode
    - ``retry=NxI`` — set retry count N and interval I seconds
    """
    if ":" not in spec:
        raise ValueError(f"update spec must look like TASK:actions (got {spec!r})")
    task_id, actions_text = spec.split(":", 1)
    task_id = task_id.strip()
    if not task_id:
        raise ValueError(f"update spec missing task id: {spec!r}")

    update = TaskErrorUpdate(task_id=task_id)
    for raw_action in actions_text.split(","):
        action = raw_action.strip()
        if not action:
            continue
        if action == "clear-retry":
            update.clear_retry = True
        elif action == "stop-on-error":
            update.error_handling = ErrorHandling.STOP
        elif action == "continue":
            update.error_handling = ErrorHandling.CONTINUE
        elif action == "error-path":
            update.error_handling = ErrorHandling.ERROR_PATH
        elif action.startswith("retry="):
            payload = action.split("=", 1)[1]
            if "x" not in payload:
                raise ValueError(f"retry action must look like retry=NxI (got {action!r})")
            count_text, interval_text = payload.split("x", 1)
            update.retry_count = int(count_text)
            update.retry_interval = int(interval_text)
        else:
            raise ValueError(f"unknown update action {action!r} in {spec!r}")
    return update


def format_task_state_lines(states: Sequence[TaskErrorState]) -> str:
    lines = ["Task error/retry state:"]
    for state in states:
        retry = "none"
        if state.retry.count is not None:
            retry = f"{state.retry.count} x every {state.retry.interval}s"
        lines.append(
            f"  {state.task_id} ({state.task_title!r}): retry={retry}, "
            f"handling={state.error_handling.value}, "
            f"continueOnError={state.continue_on_error!r}, "
            f"continueOnErrorType={state.continue_on_error_type!r}, "
            f"errorPath={state.has_error_path}"
        )
    return "\n".join(lines)
