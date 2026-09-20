"""Orchestrate clear + multi-step refactor workflows with progress reporting."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from ..runtime.graph import GraphExecutor, Task, TaskGraph
from ..settings import max_inflight_per_host
from .refactor import execute_refactor
from .refactor_cleanup import clear_refactor_playbooks
from .refactor_mode import is_parallel_mode, resolve_refactor_mode
from .refactor_presets import get_refactor_preset, resolve_workflow_preset


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


ProgressFn = Callable[[dict[str, Any]], None]


def execute_refactor_workflow(
    preset_id: str,
    *,
    skip_clear: bool = False,
    refactor_mode: Optional[str] = None,
    parallel_workers: Optional[int] = None,
    on_progress: Optional[ProgressFn] = None,
) -> dict[str, Any]:
    """Run a workflow preset (clear + one or more refactor steps)."""
    mode = resolve_refactor_mode(refactor_mode)
    preset = resolve_workflow_preset(get_refactor_preset(preset_id))
    profile = str(preset.get("profile") or "")
    if not profile:
        raise ValueError("Workflow preset requires profile")

    progress_lock = threading.Lock()

    def emit(phase: str, message: str, **extra: Any) -> None:
        if on_progress:
            with progress_lock:
                on_progress({"phase": phase, "message": message, "timestamp": _utc_now(), **extra})

    steps_out: list[dict[str, Any]] = []
    total_started = time.monotonic()
    emit("workflow.start", f"Starting workflow {preset_id} (mode={mode})", preset_id=preset_id, refactor_mode=mode)

    if not skip_clear:
        step_started = time.monotonic()
        emit("clear.start", "Clearing [REFACTOR-*] playbooks")
        clear_result = clear_refactor_playbooks(
            profile,
            name_prefix=str(preset.get("clear_refactor_prefix") or "[REFACTOR-"),
        )
        clear_elapsed = int((time.monotonic() - step_started) * 1000)
        emit(
            "clear.complete",
            f"Cleared {clear_result.get('delete_result', {}).get('counts', {}).get('deleted', 0)} playbook(s)",
            elapsed_ms=clear_elapsed,
        )
        steps_out.append({
            "step": "clear",
            "elapsed_ms": clear_elapsed,
            "ok": True,
            "result": clear_result,
        })

    refactor_steps = list(preset.get("resolved_steps") or [])
    if is_parallel_mode(mode) and len(refactor_steps) > 1:
        parallel_steps = _execute_refactor_steps_parallel(
            refactor_steps,
            profile=profile,
            workflow_id=preset_id,
            refactor_mode=mode,
            parallel_workers=parallel_workers,
            emit=emit,
        )
        steps_out.extend(parallel_steps)
    else:
        for index, step_preset in enumerate(refactor_steps, start=1):
            step_out = _execute_refactor_step_sequential(
                step_preset,
                index=index,
                total=len(refactor_steps),
                refactor_mode=mode,
                parallel_workers=parallel_workers,
                emit=emit,
            )
            steps_out.append(step_out)
            if not step_out.get("ok"):
                break

    total_elapsed_ms = int((time.monotonic() - total_started) * 1000)
    ok = all(step.get("ok") for step in steps_out)
    payload = {
        "preset_id": preset_id,
        "profile": profile,
        "refactor_mode": mode,
        "ok": ok,
        "total_elapsed_ms": total_elapsed_ms,
        "steps": steps_out,
        "finished_at": _utc_now(),
    }
    emit("workflow.complete" if ok else "workflow.failed", f"Workflow finished ok={ok}", elapsed_ms=total_elapsed_ms)
    return payload


def _execute_refactor_step_sequential(
    step_preset: dict[str, Any],
    *,
    index: int,
    total: int,
    refactor_mode: str,
    parallel_workers: Optional[int],
    emit: Callable[..., None],
) -> dict[str, Any]:
    step_id = str(step_preset.get("id") or f"step-{index}")
    step_label = str(step_preset.get("label") or step_id)
    step_started = time.monotonic()
    emit(
        "refactor.start",
        f"Refactor step {index}/{total}: {step_label}",
        step_id=step_id,
        step_index=index,
    )

    def _step_progress(event: dict[str, Any], sid: str = step_id) -> None:
        emit("refactor.progress", event.get("message") or "", step_id=sid, detail=event)

    result = execute_refactor(
        step_preset["profile"],
        playbook_name=step_preset.get("playbook_name"),
        playbook_id=step_preset.get("playbook_id"),
        leaf_tasks=step_preset.get("leaf_tasks") or [],
        clusters=step_preset.get("clusters") or [],
        post_task_updates=step_preset.get("post_task_updates") or [],
        refactor_mode=refactor_mode,
        parallel_workers=parallel_workers,
        on_progress=_step_progress,
    )
    step_elapsed = int((time.monotonic() - step_started) * 1000)
    ok = result.get("ok") is True
    emit(
        "refactor.complete" if ok else "refactor.failed",
        f"{'Completed' if ok else 'Failed'}: {step_label}",
        step_id=step_id,
        elapsed_ms=step_elapsed,
        ok=ok,
    )
    return {
        "step": step_id,
        "label": step_label,
        "elapsed_ms": step_elapsed,
        "ok": ok,
        "result": result,
    }


def _execute_refactor_steps_parallel(
    refactor_steps: list[dict[str, Any]],
    *,
    profile: str,
    workflow_id: str,
    refactor_mode: str,
    parallel_workers: Optional[int],
    emit: Callable[..., None],
) -> list[dict[str, Any]]:
    """Run independent refactor presets in parallel (experimental workflow mode)."""
    workers = parallel_workers if parallel_workers is not None else max_inflight_per_host()
    emit(
        "refactor.parallel.start",
        f"Running {len(refactor_steps)} refactor step(s) in parallel (max_workers={workers})",
        step_count=len(refactor_steps),
    )
    graph = TaskGraph()
    step_meta: dict[str, dict[str, Any]] = {}

    for index, step_preset in enumerate(refactor_steps, start=1):
        step_id = str(step_preset.get("id") or f"step-{index}")
        step_label = str(step_preset.get("label") or step_id)
        step_meta[step_id] = {"index": index, "label": step_label, "preset": step_preset}

        def _make_fn(sp: dict[str, Any], sid: str, label: str) -> Callable[[], dict[str, Any]]:
            job_cache_key = f"{workflow_id}/{sid}"

            def _run() -> dict[str, Any]:
                started = time.monotonic()
                emit(
                    "refactor.start",
                    f"Parallel refactor: {label}",
                    step_id=sid,
                    job_cache_key=job_cache_key,
                )

                def _step_progress(event: dict[str, Any], step_key: str = sid) -> None:
                    emit("refactor.progress", event.get("message") or "", step_id=step_key, detail=event)

                result = execute_refactor(
                    sp["profile"],
                    playbook_name=sp.get("playbook_name"),
                    playbook_id=sp.get("playbook_id"),
                    leaf_tasks=sp.get("leaf_tasks") or [],
                    clusters=sp.get("clusters") or [],
                    post_task_updates=sp.get("post_task_updates") or [],
                    refactor_mode=refactor_mode,
                    parallel_workers=workers,
                    on_progress=_step_progress,
                    job_cache_key=job_cache_key,
                )
                elapsed_ms = int((time.monotonic() - started) * 1000)
                ok = result.get("ok") is True
                emit(
                    "refactor.complete" if ok else "refactor.failed",
                    f"{'Completed' if ok else 'Failed'}: {label}",
                    step_id=sid,
                    elapsed_ms=elapsed_ms,
                    ok=ok,
                )
                return {
                    "step": sid,
                    "label": label,
                    "elapsed_ms": elapsed_ms,
                    "ok": ok,
                    "result": result,
                }

            return _run

        graph.add(
            Task(
                id=step_id,
                fn=_make_fn(step_preset, step_id, step_label),
                profile_slug=profile,
            )
        )

    run_result = GraphExecutor(max_workers=min(workers, len(refactor_steps))).run(graph)
    steps_out: list[dict[str, Any]] = []
    for step_id in step_meta:
        state = run_result.tasks[step_id]
        if state.status == "success":
            steps_out.append(state.result)
        else:
            meta = step_meta[step_id]
            steps_out.append({
                "step": step_id,
                "label": meta["label"],
                "elapsed_ms": 0,
                "ok": False,
                "result": {
                    "ok": False,
                    "error": state.error,
                    "failed_dependencies": state.failed_dependencies,
                },
            })
    steps_out.sort(key=lambda row: step_meta.get(str(row.get("step")), {}).get("index", 0))
    emit("refactor.parallel.complete", f"Parallel refactor batch finished ok={run_result.ok}")
    return steps_out
