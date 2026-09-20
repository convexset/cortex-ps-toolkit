from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from cortex_ps_toolkit.runtime.graph import GraphExecutor, Task, TaskGraph
from cortex_ps_toolkit.runtime.limits import LimitRegistry, reset_limit_registry


@pytest.fixture(autouse=True)
def _reset_limits() -> None:
    reset_limit_registry()


def test_graph_runs_independent_tasks_in_parallel() -> None:
    lock = threading.Lock()
    in_flight = 0
    max_in_flight = 0
    graph = TaskGraph()

    def worker(label: str) -> str:
        nonlocal in_flight, max_in_flight
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        time.sleep(0.05)
        with lock:
            in_flight -= 1
        return label

    graph.add(Task(id="a", fn=lambda: worker("a")))
    graph.add(Task(id="b", fn=lambda: worker("b")))
    result = GraphExecutor(max_workers=2).run(graph)
    assert result.ok is True
    assert max_in_flight >= 2
    assert result.task("a").status == "success"
    assert result.task("b").status == "success"


def test_failed_dependency_blocks_dependent_task() -> None:
    graph = TaskGraph()
    graph.add(Task(id="root", fn=lambda: (_ for _ in ()).throw(RuntimeError("boom"))))
    graph.add(Task(id="child", fn=lambda: "ok", depends_on=frozenset({"root"})))
    result = GraphExecutor().run(graph)
    assert result.ok is False
    assert result.task("root").status == "failed"
    child = result.task("child")
    assert child.status == "failed"
    assert child.failed_dependencies == ["root"]
    assert "Dependency failed" in (child.error or "")


def test_graph_respects_dependency_order() -> None:
    order: list[str] = []
    graph = TaskGraph()
    graph.add(Task(id="first", fn=lambda: order.append("first") or "first"))
    graph.add(
        Task(
            id="second",
            fn=lambda: order.append("second") or "second",
            depends_on=frozenset({"first"}),
        )
    )
    result = GraphExecutor().run(graph)
    assert result.ok is True
    assert order == ["first", "second"]


def test_graph_uses_limit_registry_per_host() -> None:
    registry = LimitRegistry()
    host_key = "https://tenant.example.test"
    profile = MagicMock()
    profile.host = host_key
    profile.max_inflight_per_host = 1
    profile.max_inflight_global = 10

    graph = TaskGraph()
    graph.add(
        Task(
            id="a",
            fn=lambda: time.sleep(0.08) or "a",
            host_key=host_key,
            profile_slug="lab",
        )
    )
    graph.add(
        Task(
            id="b",
            fn=lambda: time.sleep(0.08) or "b",
            host_key=host_key,
            profile_slug="lab",
        )
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "cortex_ps_toolkit.runtime.graph.get_profile",
            lambda _slug: profile,
        )
        started = time.monotonic()
        result = GraphExecutor(limit_registry=registry, max_workers=2).run(graph)
        elapsed = time.monotonic() - started

    assert result.ok is True
    assert elapsed >= 0.14
