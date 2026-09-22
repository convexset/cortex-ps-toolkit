"""Experimental parallel extract-multi variant (--parallel). Default remains sequential."""

from __future__ import annotations

import argparse
import copy
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from typing import Any, Iterator, Optional, Sequence

from .cache import PlaybookCache
from .client import PlaybookClient, insert_failure_items, unwrap_saved_playbook
from .debugio import DebugSink, slug
from .extract_multi_common import (
    ExtractMultiState,
    _compare_after_parent,
    _new_extraction_entry,
    _refresh_cache_with_log,
    finalize_extract_multi,
    prepare_extract_multi,
)
from .fields import FieldPolicy
from .keys import JsonDict
from .playbook_update import (
    expand_error_updates_from_matches,
    overwrite_playbook_description,
    overwrite_playbook_task_updates,
)
from .refactor_descriptions import descriptions_for_refactor
from .task_match import parse_post_task_update_spec


_CACHE_METHODS = ("refresh", "on_upload", "resolve", "get", "redownload_after_save", "ensure")


@contextmanager
def _locked_cache_ops(cache: PlaybookCache) -> Iterator[threading.RLock]:
    """Serialize on-disk cache mutations/reads during parallel extract-multi phases."""
    lock = threading.RLock()
    originals: dict[str, Any] = {}
    for name in _CACHE_METHODS:
        if hasattr(cache, name):
            originals[name] = getattr(cache, name)

    def _wrap(fn: Any) -> Any:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            with lock:
                return fn(*args, **kwargs)

        return wrapped

    for name, fn in originals.items():
        setattr(cache, name, _wrap(fn))
    try:
        yield lock
    finally:
        for name, fn in originals.items():
            setattr(cache, name, fn)


DEFAULT_PARALLEL_UPLOAD_WORKERS = 10


def _parallel_workers(args: argparse.Namespace, job_count: int) -> int:
    raw = getattr(args, "parallel_workers", None)
    if raw is not None:
        return max(1, min(int(raw), job_count))
    return max(1, min(5, job_count))


def _parallel_upload_workers(args: argparse.Namespace, job_count: int) -> int:
    """Sub-playbook upload pool (default 10; override with ``--parallel-upload-workers``)."""
    raw = getattr(args, "parallel_upload_workers", None)
    if raw is not None:
        return max(1, min(int(raw), job_count))
    return max(1, min(DEFAULT_PARALLEL_UPLOAD_WORKERS, job_count))


def upload_compare_subplaybooks_parallel(state: ExtractMultiState) -> Optional[int]:
    """Parallel sub uploads, single cache refresh, parallel compares."""
    from .cli import _finish_extract

    args = state.args
    workers = _parallel_upload_workers(args, len(state.jobs))
    phase1 = (
        f"Phase 1/5: Create and upload refactored sub-playbooks in parallel "
        f"({len(state.jobs)} job(s), max_workers={workers})"
    )
    state.sink.log(phase1)
    sink_lock = threading.Lock()

    entries: list[Optional[JsonDict]] = [None] * len(state.jobs)
    upload_failures: list[tuple[int, JsonDict, str]] = []

    def _upload(index: int, job: JsonDict) -> None:
        sub_name = str(job["subplaybook_name"])
        entry = _new_extraction_entry(job)
        from .extract_multi_common import yaml_for_sub_upload

        with sink_lock:
            state.sink.log(f"Uploading sub-playbook {index}/{len(state.jobs)} {sub_name!r}…")
        upload_response = state.client.save_yaml(
            yaml_for_sub_upload(state, job),
            filename=f"{slug(sub_name)}.yml",
        )
        state.cache.on_upload()
        with sink_lock:
            state.sink.log(f"Uploaded sub-playbook {index}/{len(state.jobs)} {sub_name!r}")
            state.sink.write_json(f"04-subplaybook-upload-{index:02d}.json", upload_response)
        failures = insert_failure_items(upload_response)
        already_exists = any("already exists" in str(item.get("error") or "").lower() for item in failures)
        if failures and not already_exists:
            entry["upload_error"] = failures
            label = job.get("task_id") or f"{job.get('start_task_id')}:{job.get('end_task_id')}"
            text = f"Sub-playbook upload failed for {label}:\n" + "\n".join(
                f"  {item.get('id')}: {item.get('error')}" for item in failures
            )
            upload_failures.append((index, entry, text))
            return
        saved = unwrap_saved_playbook(upload_response) or {}
        saved_id = str(saved.get("id") or "")
        entry["uploaded_subplaybook"] = {
            "id": saved_id or None,
            "name": sub_name,
            "already_exists": already_exists,
        }
        if already_exists and not args.upload_only:
            with sink_lock:
                state.sink.log(
                    f"Sub-playbook already exists; will reload {sub_name!r} after batch cache refresh"
                )
        entries[index - 1] = entry

    with _locked_cache_ops(state.cache):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_upload, index, job) for index, job in enumerate(state.jobs, 1)]
            for future in as_completed(futures):
                future.result()

    if upload_failures:
        upload_failures.sort(key=lambda row: row[0])
        index, entry, text = upload_failures[0]
        state.result["extractions"] = [entry]
        return _finish_extract(args, state.client, state.cache, state.sink, state.result, exit_code=1, text=text)

    state.result["extractions"] = [entry for entry in entries if entry is not None]

    if args.upload_only:
        return None

    defer = _compare_after_parent(args)
    with _locked_cache_ops(state.cache):
        refresh_exit = _refresh_cache_with_log(
            state,
            phase="Phase 2/5: Pause and refresh cache" if defer else "Refreshing playbook cache before compare (parallel)",
        )
        if refresh_exit is not None:
            return refresh_exit

        if defer:
            state.sink.log("Deferring sub-playbook compare until after parent upload (legacy --compare-after-parent)")
            return None

        compare_workers = _parallel_workers(args, len(state.jobs))
        state.sink.log(
            f"Phase 3/5: Comparing uploaded sub-playbooks ({len(state.jobs)} job(s), max_workers={compare_workers})"
        )
        compare_subplaybooks_parallel(state)
    return None


def compare_subplaybooks_parallel(state: ExtractMultiState) -> None:
    """Parallel round-trip compares (Phase 5 or inline parallel path)."""
    args = state.args
    workers = _parallel_workers(args, len(state.jobs))
    compare_sink_lock = threading.Lock()

    def _compare(index: int, job: JsonDict, entry: JsonDict) -> tuple[int, bool]:
        mismatch = False
        sub_name = str(entry.get("subplaybook_name") or "")
        try:
            downloaded = state.cache.resolve(sub_name, force=False)
        except Exception as exc:
            entry["download_error"] = str(exc)
            return index, True
        with compare_sink_lock:
            state.sink.write_json(f"05-subplaybook-downloaded-{index:02d}.json", downloaded)
        entry["uploaded_subplaybook"] = {
            "id": downloaded.get("id"),
            "name": downloaded.get("name"),
        }
        sub_id = str(downloaded.get("id") or "") or None
        if job["kind"] == "cluster":
            from .compare import (
                compare_source_to_downloaded_cluster_subplaybook,
                format_compare_log_line,
                summarize_diff_paths,
            )

            compared = compare_source_to_downloaded_cluster_subplaybook(
                state.playbook,
                job["cluster_check"],
                downloaded,
                policy=state.policy,
                cache=state.cache,
            )
            label = f"{job['start_task_id']}:{job['end_task_id']}"
        else:
            from .compare import (
                compare_source_to_downloaded_subplaybook,
                format_compare_log_line,
                summarize_diff_paths,
            )

            root_check = job["root_check"]
            compared = compare_source_to_downloaded_subplaybook(
                state.playbook,
                str(job["task_id"]),
                downloaded,
                policy=state.policy,
                allowed_task_ids=set(root_check.descendant_ids),
                cache=state.cache,
            )
            label = str(job["task_id"])
        with compare_sink_lock:
            state.sink.write_json(f"06-compare-{index:02d}.json", compared.to_dict())
            state.sink.write_text(f"06-compare-{index:02d}.txt", compared.human_summary())
            state.sink.log(format_compare_log_line(compared, label))
        entry["compare"] = {
            "equal": compared.equal,
            "diff_count": len(compared.diffs),
            "diff_counts": summarize_diff_paths(compared.diffs),
        }
        if not compared.equal:
            mismatch = True
        state.sub_ids[index - 1] = sub_id
        return index, mismatch

    with _locked_cache_ops(state.cache):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(_compare, index, job, entry)
                for index, (job, entry) in enumerate(zip(state.jobs, state.result["extractions"]), 1)
            ]
            for future in as_completed(futures):
                _index, mismatch = future.result()
                if mismatch:
                    state.any_mismatch = True


def run_post_task_updates_parallel(
    *,
    client: PlaybookClient,
    cache: PlaybookCache,
    policy: FieldPolicy,
    playbook_names: Sequence[str],
    post_specs: Sequence[str],
    sink: DebugSink,
    args: argparse.Namespace,
) -> JsonDict:
    from .cli import _dedupe_error_updates

    rules = [parse_post_task_update_spec(spec) for spec in post_specs]
    workers = _parallel_workers(args, len(playbook_names))
    sink.log(f"Parallel post-task updates: {len(playbook_names)} playbook(s), max_workers={workers}")
    sink_lock = threading.Lock()
    outcomes: list[Optional[JsonDict]] = [None] * len(playbook_names)
    pending_validation: list[tuple[int, JsonDict]] = []

    def _update(index: int, name: str) -> None:
        playbook = cache.resolve(name, force=False)
        error_updates: list = []
        rejected: list[JsonDict] = []
        for match, actions in rules:
            expanded, rule_rejected = expand_error_updates_from_matches(playbook, [match], actions)
            error_updates.extend(expanded)
            rejected.extend(rule_rejected)
        error_updates = _dedupe_error_updates(error_updates)
        with sink_lock:
            sink.write_json(f"11-post-update-source-{index:02d}.json", playbook)
        if not error_updates:
            with sink_lock:
                sink.log(f"Post-update skip {name!r}: no matching regular script tasks")
            outcomes[index - 1] = {
                "playbook_name": name,
                "ok": True,
                "skipped": True,
                "reason": "no matching tasks",
                "error_rejected": rejected,
            }
            return
        outcome = overwrite_playbook_task_updates(
            client=client,
            cache=cache,
            policy=policy,
            playbook=playbook,
            error_updates=error_updates,
            context_updates=[],
            sink=sink,
            defer_cache_refresh=True,
        )
        outcome["error_rejected"] = list(outcome.get("error_rejected") or []) + rejected
        if rejected:
            outcome["ok"] = False
        ctx = outcome.pop("_validation_ctx", None)
        if ctx is not None:
            pending_validation.append((index - 1, ctx))
        outcomes[index - 1] = outcome

    with _locked_cache_ops(cache):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_update, index, name) for index, name in enumerate(playbook_names, 1)]
            for future in as_completed(futures):
                future.result()
        if pending_validation:
            sink.log(
                f"Refreshing cache once after {len(pending_validation)} post-task upload(s) (parallel path)"
            )
            cache.invalidate()
            cache.refresh()
            from .playbook_update import _validate_uploaded_task_updates

            for idx, ctx in pending_validation:
                validated = _validate_uploaded_task_updates(cache=cache, **ctx)
                row = outcomes[idx]
                if row is None:
                    continue
                row.update(validated)
                row.pop("validation_deferred", None)
                sink.write_json(f"11-post-update-outcome-{idx + 1:02d}.json", row)

    resolved = [row for row in outcomes if row is not None]
    return {
        "playbook_count": len(playbook_names),
        "ok": all(row.get("ok") for row in resolved),
        "outcomes": resolved,
        "execution_variant": "parallel",
    }


def apply_refactor_descriptions_parallel(
    *,
    client: PlaybookClient,
    cache: PlaybookCache,
    policy: FieldPolicy,
    sink: DebugSink,
    source: JsonDict,
    parent: JsonDict,
    post_result: Optional[JsonDict],
    post_specs: Sequence[str],
    args: argparse.Namespace,
    skip_sub_uploads: bool = False,
) -> tuple[JsonDict, JsonDict]:
    refactor = parent.get("_refactor") or {}
    payload = descriptions_for_refactor(
        source=source,
        refactor=refactor,
        post_result=post_result,
        post_specs=post_specs,
    )
    sink.write_json("12-refactor-descriptions.json", payload)
    sink.write_text("12-parent-description.txt", str(payload.get("parent_description") or ""))
    sink.write_text("12-refactor-metrics.txt", str(payload.get("metrics_log") or ""))
    sink.log("Refactor metrics written to 12-refactor-metrics.txt")

    sub_items = sorted((payload.get("sub_descriptions") or {}).items())
    for index, (sub_name, description) in enumerate(sub_items, 1):
        sink.write_text(f"12-sub-description-{index:02d}.txt", description)

    sub_outcomes: list[JsonDict] = []
    if skip_sub_uploads:
        sink.log("Sub-playbook descriptions were set on initial upload; skipping sub description overwrites")
        sub_outcomes = [
            {"playbook_name": sub_name, "ok": True, "skipped": True, "reason": "embedded_at_upload"}
            for sub_name, _description in sub_items
        ]
    else:
        workers = _parallel_workers(args, max(1, len(sub_items)))
        sink.log(f"Parallel description uploads: {len(sub_items)} sub-playbook(s), max_workers={workers}")
        sink_lock = threading.Lock()
        pending: list[Optional[JsonDict]] = [None] * len(sub_items)

        def _apply(index: int, sub_name: str, description: str) -> None:
            try:
                sub_playbook = cache.resolve(sub_name, force=False)
            except Exception as exc:
                with sink_lock:
                    sink.log(f"Could not resolve sub-playbook {sub_name!r} for description overwrite: {exc}")
                pending[index - 1] = {
                    "playbook_name": sub_name,
                    "ok": False,
                    "error": str(exc),
                }
                return
            outcome = overwrite_playbook_description(
                client=client,
                cache=cache,
                policy=policy,
                playbook=sub_playbook,
                description=description,
                sink=sink,
            )
            with sink_lock:
                sink.write_json(f"12-sub-description-upload-{index:02d}.json", outcome)
            pending[index - 1] = outcome

        with _locked_cache_ops(cache):
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(_apply, index, sub_name, description)
                    for index, (sub_name, description) in enumerate(sub_items, 1)
                ]
                for future in as_completed(futures):
                    future.result()
        sub_outcomes = [row for row in pending if row is not None]

    resolved = sub_outcomes
    parent = copy.deepcopy(parent)
    parent["description"] = str(payload.get("parent_description") or "")
    parent.pop("comment", None)
    result = {
        "ok": all(row.get("ok") for row in resolved) if resolved else True,
        "sub_outcomes": resolved,
        "extraction_count": payload.get("extraction_count"),
        "httpv2_task_count": payload.get("httpv2_task_count"),
        "execution_variant": "parallel",
    }
    return parent, result


def run_extract_multi_parallel(args: argparse.Namespace) -> int:
    """Entry point for --parallel extract-multi (experimental)."""
    state = prepare_extract_multi(args)
    state.execution_variant = "parallel"
    state.result["execution_variant"] = "parallel"
    early_exit = upload_compare_subplaybooks_parallel(state)
    if early_exit is not None:
        return early_exit
    return finalize_extract_multi(state, parallel_post_steps=True)
