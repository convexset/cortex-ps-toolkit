"""Dependency-graph task runner with thread pool and concurrency limits."""

from __future__ import annotations

import enum
import threading
import traceback
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .limits import LimitRegistry, get_limit_registry, profile_host_key

from ..credentials import CredentialProfile, get_profile


class RefreshMode(str, enum.Enum):
    """Cache refresh intent — elective skips when TTL-fresh; required always fetches."""

    ELECTIVE = "elective"
    REQUIRED = "required"


@dataclass(frozen=True)
class Task:
    id: str
    fn: Callable[[], Any]
    depends_on: frozenset[str] = frozenset()
    host_key: Optional[str] = None
    profile_slug: Optional[str] = None


@dataclass
class TaskState:
    id: str
    status: str
    result: Any = None
    error: Optional[str] = None
    failed_dependencies: list[str] = field(default_factory=list)


@dataclass
class GraphRunResult:
    ok: bool
    tasks: dict[str, TaskState]

    def task(self, task_id: str) -> TaskState:
        return self.tasks[task_id]


class TaskGraph:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def add(self, task: Task) -> None:
        if task.id in self._tasks:
            raise ValueError(f"Duplicate task id {task.id!r}")
        self._tasks[task.id] = task

    def tasks(self) -> dict[str, Task]:
        return dict(self._tasks)

    def validate(self) -> None:
        for task in self._tasks.values():
            unknown = task.depends_on - set(self._tasks)
            if unknown:
                raise ValueError(f"Task {task.id!r} has unknown dependencies: {sorted(unknown)}")


class GraphExecutor:
    def __init__(
        self,
        *,
        limit_registry: Optional[LimitRegistry] = None,
        max_workers: Optional[int] = None,
    ) -> None:
        self._limits = limit_registry or get_limit_registry()
        self._max_workers = max_workers

    def run(self, graph: TaskGraph) -> GraphRunResult:
        graph.validate()
        tasks = graph.tasks()
        if not tasks:
            return GraphRunResult(ok=True, tasks={})

        states: dict[str, TaskState] = {
            task_id: TaskState(id=task_id, status="pending") for task_id in tasks
        }
        completed: set[str] = set()
        failed: set[str] = set()
        lock = threading.Lock()

        def _resolve_profile(slug: Optional[str]) -> Optional[CredentialProfile]:
            if not slug:
                return None
            try:
                return get_profile(slug)
            except KeyError:
                return None

        def _run_task(task: Task) -> None:
            profile = _resolve_profile(task.profile_slug)
            host = task.host_key
            if host is None and profile is not None:
                host = profile_host_key(profile)
            try:
                with self._limits.acquire(host_key=host, profile=profile):
                    result = task.fn()
                with lock:
                    states[task.id].status = "success"
                    states[task.id].result = result
                    completed.add(task.id)
            except Exception as exc:
                with lock:
                    states[task.id].status = "failed"
                    states[task.id].error = str(exc)
                    failed.add(task.id)

        def _mark_blocked(task_id: str, bad_deps: list[str]) -> None:
            states[task_id].status = "failed"
            states[task_id].failed_dependencies = bad_deps
            states[task_id].error = f"Dependency failed: {', '.join(bad_deps)}"
            failed.add(task_id)

        workers = self._max_workers
        if workers is None:
            workers = min(32, max(4, len(tasks)))

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures: dict[str, Future[None]] = {}

            while True:
                with lock:
                    ready: list[Task] = []
                    for task_id, task in tasks.items():
                        if task_id in completed or task_id in failed or task_id in futures:
                            continue
                        bad = [dep for dep in task.depends_on if dep in failed]
                        if bad:
                            _mark_blocked(task_id, bad)
                            continue
                        if task.depends_on <= completed:
                            ready.append(task)

                    if not ready and not futures:
                        break

                for task in ready:
                    futures[task.id] = pool.submit(_run_task, task)

                if not futures:
                    continue

                done, _pending = wait(futures.values(), return_when="FIRST_COMPLETED")
                for future in done:
                    with lock:
                        to_remove = [tid for tid, fut in futures.items() if fut is future]
                    for tid in to_remove:
                        futures.pop(tid, None)
                        try:
                            future.result()
                        except Exception as exc:
                            with lock:
                                if states[tid].status == "pending":
                                    states[tid].status = "failed"
                                    states[tid].error = str(exc)
                                    failed.add(tid)

                with lock:
                    if len(completed) + len(failed) >= len(tasks):
                        break

        ok = all(state.status == "success" for state in states.values())
        return GraphRunResult(ok=ok, tasks=states)
