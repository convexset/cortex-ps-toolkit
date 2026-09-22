"""Validate uploaded refactor jobs after a single cache refresh."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from .cache import PlaybookCache
from .client import PlaybookClient
from .compare import compare_source_to_downloaded_subplaybook, summarize_diff_paths, unfiltered_field_policy
from .delete import delete_playbook_rows, order_playbooks_for_delete
from .debugio import DebugSink
from .fields import FieldPolicy
from .keys import JsonDict


def load_jobs(path: Path) -> list[JsonDict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "jobs" in data:
        raw = data["jobs"]
    elif isinstance(data, list):
        raw = data
    else:
        raise ValueError(f"jobs file must be a JSON array or {{jobs: [...]}}: {path}")
    if not isinstance(raw, list):
        raise ValueError(f"jobs must be a list: {path}")
    return [dict(item) for item in raw]


def job_upload_names(job: Mapping[str, Any]) -> tuple[str, str]:
    sub_name = str(
        job.get("subplaybook_name")
        or (job.get("uploaded_subplaybook") or {}).get("name")
        or ""
    )
    parent_name = str(
        job.get("parent_copy_name")
        or (job.get("parent") or {}).get("name")
        or ""
    )
    return sub_name, parent_name


def job_source_ref(job: Mapping[str, Any]) -> str:
    source = job.get("source_playbook") or {}
    return str(source.get("name") or source.get("id") or job.get("source_name") or "")


def job_task_id(job: Mapping[str, Any]) -> str:
    return str(job.get("task_id") or "")


def merge_job_manifests(paths: Sequence[Path]) -> list[JsonDict]:
    jobs: list[JsonDict] = []
    for path in paths:
        jobs.extend(load_jobs(path))
    return jobs


def validate_jobs(
    jobs: Sequence[Mapping[str, Any]],
    *,
    cache: PlaybookCache,
    client: PlaybookClient,
    policy: FieldPolicy,
    sink: DebugSink,
    keep_failures: bool = False,
    refresh_before: bool = True,
    refresh_after_deletes: bool = True,
    log: Optional[Callable[[str], None]] = None,
) -> JsonDict:
    """Refresh once, compare each job, delete failures unless keep_failures."""
    say = log or sink.log
    if refresh_before:
        say("Refreshing playbook cache before validation")
        cache.refresh()

    results: list[JsonDict] = []
    to_delete: list[JsonDict] = []
    equal_count = 0
    mismatch_count = 0
    skipped_count = 0
    delete_failures = 0

    for index, job in enumerate(jobs, 1):
        source_ref = job_source_ref(job)
        task_id = job_task_id(job)
        sub_name, parent_name = job_upload_names(job)
        entry: JsonDict = {
            "index": index,
            "source_playbook": job.get("source_playbook"),
            "task_id": task_id,
            "subplaybook_name": sub_name,
            "parent_copy_name": parent_name,
            "upload_error": job.get("upload_error"),
            "skipped": False,
            "equal": None,
            "diff_count": None,
            "diff_counts": None,
            "deleted": False,
            "error": None,
        }
        if job.get("upload_error"):
            entry["skipped"] = True
            entry["error"] = "upload failed"
            skipped_count += 1
            results.append(entry)
            continue
        if not source_ref or not task_id or not sub_name:
            entry["skipped"] = True
            entry["error"] = "missing source_playbook, task_id, or subplaybook_name"
            skipped_count += 1
            results.append(entry)
            continue

        try:
            source = cache.resolve(source_ref, force=False)
            downloaded = cache.resolve(sub_name, force=False)
            compared = compare_source_to_downloaded_subplaybook(source, task_id, downloaded, policy=policy)
            entry["equal"] = compared.equal
            entry["diff_count"] = len(compared.diffs)
            entry["diff_counts"] = summarize_diff_paths(compared.diffs)
            entry["compare"] = {
                "equal": compared.equal,
                "diff_count": len(compared.diffs),
                "diff_counts": summarize_diff_paths(compared.diffs),
                "left_root": compared.left_root,
                "right_root": compared.right_root,
            }
            unfiltered = compare_source_to_downloaded_subplaybook(
                source, task_id, downloaded, policy=unfiltered_field_policy()
            )
            entry["compare_all_fields"] = {
                "equal": unfiltered.equal,
                "diff_count": len(unfiltered.diffs),
                "diff_counts": summarize_diff_paths(unfiltered.diffs),
            }
            if compared.equal:
                equal_count += 1
                say(f"[{index}/{len(jobs)}] OK {source_ref!r} task={task_id}")
            else:
                mismatch_count += 1
                say(
                    f"[{index}/{len(jobs)}] MISMATCH {source_ref!r} task={task_id} "
                    f"diffs={len(compared.diffs)}"
                )
                if not keep_failures:
                    rows = []
                    if parent_name:
                        rows.append({"name": parent_name})
                    rows.append({"name": sub_name, "id": str(downloaded.get("id") or "")})
                    to_delete.extend(rows)
                    entry["deleted"] = True
        except Exception as exc:
            entry["error"] = str(exc)
            mismatch_count += 1
            say(f"[{index}/{len(jobs)}] ERROR {source_ref!r}: {exc}")
            if not keep_failures and sub_name:
                rows = [{"name": parent_name}] if parent_name else []
                rows.append({"name": sub_name})
                to_delete.extend(rows)
                entry["deleted"] = True
        results.append(entry)

    delete_outcomes: list[JsonDict] = []
    if to_delete:
        ordered = order_playbooks_for_delete(to_delete)
        sink.write_json("01-delete-order.json", ordered)
        delete_outcomes = delete_playbook_rows(ordered, delete_fn=client.delete_playbook, log=say)
        cache.on_delete()
        delete_failures = sum(1 for row in delete_outcomes if not row.get("ok"))
        sink.write_json("02-delete-outcomes.json", delete_outcomes)
        if refresh_after_deletes:
            say("Refreshing playbook cache after deletes")
            cache.refresh()

    payload: JsonDict = {
        "job_count": len(jobs),
        "equal": equal_count,
        "mismatch": mismatch_count,
        "skipped": skipped_count,
        "keep_failures": keep_failures,
        "deleted_rows": len(delete_outcomes),
        "delete_failures": delete_failures,
        "results": results,
    }
    return payload
