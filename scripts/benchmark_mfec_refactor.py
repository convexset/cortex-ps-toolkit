#!/usr/bin/env python3
"""Benchmark clear + refactor workflow on MFEC UAT; store detailed timing JSON."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cortex_ps_toolkit.paths import data_dir
from cortex_ps_toolkit.playbooks.refactor import execute_refactor
from cortex_ps_toolkit.playbooks.refactor_cleanup import clear_refactor_playbooks
from cortex_ps_toolkit.playbooks.refactor_presets import get_refactor_preset, resolve_workflow_preset
from cortex_ps_toolkit.playbooks.refactor_workflow import execute_refactor_workflow


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _timed(label: str, fn: Callable[[], dict[str, Any]], *, progress: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    started = time.monotonic()
    started_at = _utc_now()
    error: Optional[str] = None
    result: dict[str, Any] = {}
    try:
        result = fn()
    except Exception as exc:
        error = str(exc)
        result = {"ok": False, "error": str(exc)}
    elapsed_ms = int((time.monotonic() - started) * 1000)
    entry = {
        "label": label,
        "started_at": started_at,
        "elapsed_ms": elapsed_ms,
        "ok": error is None and result.get("ok", True) is not False,
        "error": error,
        "result_summary": _summarize_result(result),
        "result": result,
    }
    if progress is not None:
        entry["progress_events"] = list(progress)
    return entry


def _summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {"ok": result.get("ok")}
    if "exit_code" in result:
        summary["exit_code"] = result.get("exit_code")
    if "parent" in result and isinstance(result["parent"], dict):
        summary["parent_name"] = result["parent"].get("name")
    if "parent_copy_name" in result:
        summary["parent_copy_name"] = result.get("parent_copy_name")
    compares = result.get("compares") or result.get("compare_results")
    if isinstance(compares, list):
        summary["compare_equal"] = sum(1 for row in compares if row.get("equal") is True)
        summary["compare_total"] = len(compares)
    if "timing" in result:
        summary["timing"] = result["timing"]
    if "debug_dir" in result:
        summary["debug_dir"] = result.get("debug_dir")
    counts = (result.get("delete_result") or {}).get("counts")
    if counts:
        summary["deleted_count"] = counts.get("deleted")
    return summary


def run_step_refactor(
    preset: dict[str, Any],
    *,
    refactor_mode: str | None = None,
    on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    progress_log: list[dict[str, Any]] = []

    def _progress(event: dict[str, Any]) -> None:
        progress_log.append({**event, "at": _utc_now()})
        if on_progress:
            on_progress(event)

    def _run() -> dict[str, Any]:
        payload = execute_refactor(
            preset["profile"],
            playbook_name=preset.get("playbook_name"),
            playbook_id=preset.get("playbook_id"),
            leaf_tasks=preset.get("leaf_tasks") or [],
            clusters=preset.get("clusters") or [],
            post_task_updates=preset.get("post_task_updates") or [],
            refactor_mode=refactor_mode,
            on_progress=_progress,
        )
        payload["_progress_events"] = progress_log
        return payload

    return _timed(preset.get("label") or preset.get("id") or "refactor", _run, progress=progress_log)


def run_benchmark(
    *,
    label: str,
    profile: str = "mfec-uat",
    skip_clear: bool = False,
    skip_splunk: bool = False,
    skip_sim: bool = False,
    dry_run_clear: bool = False,
    stream_progress: bool = False,
    via_workflow: bool = False,
    refactor_mode: str | None = None,
) -> dict[str, Any]:
    total_started = time.monotonic()
    steps: list[dict[str, Any]] = []

    if via_workflow:
        progress_log: list[dict[str, Any]] = []

        def _workflow_progress(event: dict[str, Any]) -> None:
            progress_log.append({**event, "at": _utc_now()})
            if stream_progress:
                print(event.get("message") or event, flush=True)

        def _run_workflow() -> dict[str, Any]:
            result = execute_refactor_workflow(
                "mfec-uat-full-workflow",
                skip_clear=skip_clear,
                refactor_mode=refactor_mode,
                on_progress=_workflow_progress if stream_progress else None,
            )
            result["_progress_events"] = progress_log
            return result

        steps.append(_timed("mfec-uat-full-workflow", _run_workflow, progress=progress_log if stream_progress else None))
    else:
        workflow = resolve_workflow_preset(get_refactor_preset("mfec-uat-full-workflow"))
        prefix = workflow.get("clear_refactor_prefix") or "[REFACTOR-"

        if not skip_clear:
            clear_entry = _timed(
                "clear_refactor_playbooks",
                lambda: clear_refactor_playbooks(
                    profile,
                    name_prefix=prefix,
                    dry_run=dry_run_clear,
                ),
            )
            steps.append(clear_entry)

        step_presets = workflow.get("resolved_steps") or []
        for step_preset in step_presets:
            step_id = step_preset.get("id") or ""
            if skip_splunk and "splunk" in step_id:
                continue
            if skip_sim and "sim" in step_id:
                continue

            def _printer(event: dict[str, Any], sid: str = step_id) -> None:
                if stream_progress:
                    print(f"[{sid}] {event.get('message') or event}", flush=True)

            steps.append(
                run_step_refactor(
                    step_preset,
                    refactor_mode=refactor_mode,
                    on_progress=_printer if stream_progress else None,
                )
            )

    total_elapsed_ms = int((time.monotonic() - total_started) * 1000)
    return {
        "benchmark_label": label,
        "profile": profile,
        "mode": "workflow" if via_workflow else "stepwise",
        "refactor_mode": refactor_mode or "sequential",
        "stream_progress": stream_progress,
        "started_at": steps[0]["started_at"] if steps else _utc_now(),
        "finished_at": _utc_now(),
        "total_elapsed_ms": total_elapsed_ms,
        "ok": all(step.get("ok") for step in steps),
        "steps": steps,
    }


def _default_output_path(label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label).strip("-")
    out_dir = data_dir() / "refactor-benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{stamp}-{safe}.json"


def _flatten_step_timings(report: dict[str, Any]) -> dict[str, int]:
    timings: dict[str, int] = {}
    for step in report.get("steps") or []:
        label = str(step.get("label") or "")
        elapsed = int(step.get("elapsed_ms") or 0)
        if label == "mfec-uat-full-workflow":
            inner = (step.get("result") or {}).get("steps") or []
            for inner_step in inner:
                inner_label = str(inner_step.get("label") or inner_step.get("step") or "")
                if inner_label == "clear":
                    timings["clear_refactor_playbooks"] = int(inner_step.get("elapsed_ms") or 0)
                elif inner_label:
                    timings[inner_label] = int(inner_step.get("elapsed_ms") or 0)
        elif label:
            timings[label] = elapsed
    return timings


def compare_reports(path_a: Path, path_b: Path) -> dict[str, Any]:
    report_a = json.loads(path_a.read_text(encoding="utf-8"))
    report_b = json.loads(path_b.read_text(encoding="utf-8"))
    steps_a = _flatten_step_timings(report_a)
    steps_b = _flatten_step_timings(report_b)
    comparisons: list[dict[str, Any]] = []
    label_map = {
        "mfec-uat-splunk-phishing": "MFEC UAT — Splunk Phishing",
        "mfec-uat-sim-phishing": "MFEC UAT — SIM Phishing",
    }
    for label in sorted(set(steps_a) | set(steps_b)):
        elapsed_a = int(steps_a.get(label) or 0)
        elapsed_b = int(steps_b.get(label) or 0)
        delta = elapsed_b - elapsed_a
        display = label_map.get(label, label)
        comparisons.append({
            "label": display,
            "step_key": label,
            "baseline_ms": elapsed_a,
            "candidate_ms": elapsed_b,
            "delta_ms": delta,
            "delta_pct": round((delta / elapsed_a) * 100, 1) if elapsed_a else None,
        })
    return {
        "baseline": {"label": report_a.get("benchmark_label"), "path": str(path_a), "total_ms": report_a.get("total_elapsed_ms")},
        "candidate": {"label": report_b.get("benchmark_label"), "path": str(path_b), "total_ms": report_b.get("total_elapsed_ms")},
        "total_delta_ms": int((report_b.get("total_elapsed_ms") or 0) - (report_a.get("total_elapsed_ms") or 0)),
        "steps": comparisons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="baseline-bridge", help="Run label stored in the report")
    parser.add_argument("--profile", default="mfec-uat")
    parser.add_argument("--output", type=Path, help="Output JSON path")
    parser.add_argument("--skip-clear", action="store_true")
    parser.add_argument("--skip-splunk", action="store_true")
    parser.add_argument("--skip-sim", action="store_true")
    parser.add_argument("--dry-run-clear", action="store_true")
    parser.add_argument("--stream-progress", action="store_true")
    parser.add_argument("--via-workflow", action="store_true", help="Use execute_refactor_workflow (toolkit port)")
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Use experimental parallel refactor mode (extract-multi + workflow steps)",
    )
    parser.add_argument("--compare", nargs=2, metavar=("BASELINE", "CANDIDATE"), type=Path)
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        metavar="N",
        help="Run the benchmark N times (writes numbered outputs when N>1)",
    )
    args = parser.parse_args()

    if args.compare:
        comparison = compare_reports(args.compare[0], args.compare[1])
        out = args.output or _default_output_path("comparison")
        out.write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(comparison, indent=2))
        print(f"\nWrote comparison to {out}")
        return 0

    repeat = max(1, int(args.repeat or 1))
    exit_code = 0
    runs: list[dict[str, Any]] = []
    for index in range(repeat):
        run_label = args.label if repeat == 1 else f"{args.label}-run{index + 1}"
        report = run_benchmark(
            label=run_label,
            profile=args.profile,
            skip_clear=args.skip_clear,
            skip_splunk=args.skip_splunk,
            skip_sim=args.skip_sim,
            dry_run_clear=args.dry_run_clear,
            stream_progress=args.stream_progress,
            via_workflow=args.via_workflow,
            refactor_mode="parallel" if args.parallel else None,
        )
        runs.append(report)
        out = args.output if repeat == 1 and args.output else _default_output_path(run_label)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"ok": report["ok"], "total_elapsed_ms": report["total_elapsed_ms"], "output": str(out)}, indent=2))
        for step in report["steps"]:
            print(f"  {step['label']}: {step['elapsed_ms']}ms ok={step['ok']}")
        if not report["ok"]:
            exit_code = 1
    if repeat > 1:
        totals = [int(row.get("total_elapsed_ms") or 0) for row in runs]
        summary = {
            "repeat": repeat,
            "ok": all(row.get("ok") for row in runs),
            "total_elapsed_ms": totals,
            "min_ms": min(totals) if totals else 0,
            "max_ms": max(totals) if totals else 0,
            "avg_ms": int(sum(totals) / len(totals)) if totals else 0,
        }
        print(json.dumps(summary, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
