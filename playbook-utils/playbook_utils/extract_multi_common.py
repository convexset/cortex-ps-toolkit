"""Shared extract-multi preparation and finalization (sequential + parallel variants)."""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from .bindings import prepare_playbook_for_yaml_export
from .cache import PlaybookCache
from .client import PlaybookClient, insert_failure_items, unwrap_saved_playbook
from .compare import (
    compare_source_to_downloaded_cluster_subplaybook,
    compare_source_to_downloaded_subplaybook,
    format_compare_log_line,
    summarize_diff_paths,
)
from .credentials import Credentials
from .debugio import DebugSink, slug
from .extract import (
    build_subplaybook,
    build_subplaybook_cluster,
    refactor_cluster_subplaybook_name,
    refactor_parent_copy_name,
    refactor_subplaybook_name,
    rewrite_parent_cluster,
    rewrite_parent_combined,
    rewrite_parent_multi,
)
from .fields import FieldPolicy
from .graph import check_combined_extract
from .inspect import resolve_task_ref
from .keys import JsonDict, playbook_tasks, task_name
from .refactor_descriptions import embed_sub_playbook_description_on_job
from .yaml_codec import dumps_yaml


def overwrite_existing_enabled(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "overwrite_existing", False))


def yaml_for_sub_upload(state: "ExtractMultiState", job: JsonDict) -> str:
    """Build sub-playbook YAML for upload; use in-place overwrite when configured."""
    base_kwargs = {
        "policy": state.policy,
        "script_names": state.script_names,
        "playbook_names": state.playbook_names,
        "bind_subplaybooks_by_id": state.bind_by_id,
    }
    if not overwrite_existing_enabled(state.args):
        return dumps_yaml(job["sub"], **base_kwargs)
    sub_name = str(job["subplaybook_name"])
    try:
        existing = state.cache.resolve_index_only(sub_name)
    except KeyError:
        return dumps_yaml(job["sub"], **base_kwargs)
    sub = copy.deepcopy(job["sub"])
    existing_id = str(existing.get("id") or "")
    if existing_id:
        sub["id"] = existing_id
    state.sink.log(f"Overwrite enabled: replacing existing sub-playbook {sub_name!r} ({existing_id})")
    return dumps_yaml(sub, **base_kwargs, overwrite=True)


def yaml_for_parent_upload(state: "ExtractMultiState", parent: JsonDict) -> str:
    """Build parent copy YAML; use in-place overwrite when a same-name playbook exists."""
    if not overwrite_existing_enabled(state.args):
        return dumps_yaml(
            parent,
            policy=state.policy,
            script_names=state.script_names,
            playbook_names=state.playbook_names,
            bind_subplaybooks_by_id=state.bind_by_id,
        )
    copy_name = str(state.parent_copy_name)
    try:
        existing = state.cache.resolve_index_only(copy_name)
    except KeyError:
        return dumps_yaml(
            parent,
            policy=state.policy,
            script_names=state.script_names,
            playbook_names=state.playbook_names,
            bind_subplaybooks_by_id=state.bind_by_id,
        )
    merged = copy.deepcopy(parent)
    existing_id = str(existing.get("id") or "")
    if existing_id:
        merged["id"] = existing_id
    state.sink.log(f"Overwrite enabled: replacing existing parent copy {copy_name!r} ({existing_id})")
    return dumps_yaml(
        merged,
        policy=state.policy,
        script_names=state.script_names,
        playbook_names=state.playbook_names,
        bind_subplaybooks_by_id=state.bind_by_id,
        overwrite=True,
    )


@dataclass
class ExtractMultiState:
    args: argparse.Namespace
    creds: Credentials
    client: PlaybookClient
    cache: PlaybookCache
    policy: FieldPolicy
    sink: DebugSink
    playbook: JsonDict
    jobs: list[JsonDict]
    result: JsonDict
    combined_check: Any
    parent_copy_name: str
    task_ids: list[str]
    bind_by_id: bool
    script_names: JsonDict
    playbook_names: JsonDict
    sub_ids: list[Optional[str]] = field(default_factory=list)
    any_mismatch: bool = False
    cache_refreshed: bool = False
    execution_variant: str = "sequential"


def prepare_extract_multi(args: argparse.Namespace) -> ExtractMultiState:
    """Build sub-playbook jobs and result skeleton (shared by sequential and parallel paths)."""
    from .cli import _load_script_and_playbook_names, _parse_cluster_ref, _runtime, _sink_for

    creds, client, cache, policy = _runtime(args)
    task_refs = list(args.tasks or [])
    cluster_specs = list(args.clusters or [])
    if not task_refs and not cluster_specs:
        raise SystemExit("error: extract-multi requires at least one --task and/or --cluster START:END")

    label_parts = task_refs + cluster_specs
    sink = _sink_for(args, f"extract-multi-{args.playbook}-{'-'.join(label_parts)}")
    playbook = cache.resolve(args.playbook, force=args.force)
    sink.write_json("01-source-playbook.json", playbook)
    sink.write_json("00-field-policy.json", policy.to_dict())

    task_ids = [resolve_task_ref(playbook, ref) for ref in task_refs]
    cluster_pairs = [_parse_cluster_ref(playbook, spec) for spec in cluster_specs]
    combined_check = check_combined_extract(playbook, task_ids, cluster_pairs)
    sink.write_json("02-multi-extract-check.json", combined_check.to_dict())
    if not combined_check.ok:
        from .cli import _emit

        text = "Multi-extract preflight failed:\n" + "\n".join(
            f"  - {reason}" for reason in combined_check.reasons
        )
        _emit(sink, args, combined_check.to_dict(), text=text)
        raise SystemExit(2)

    parent_name = str(playbook.get("name") or "playbook")
    parent_copy_name = args.parent_copy_name or refactor_parent_copy_name(parent_name)
    tasks_map = playbook_tasks(playbook)

    jobs: list[JsonDict] = []
    for cluster_check in combined_check.clusters:
        start_id = cluster_check.start_task_id
        end_id = cluster_check.end_task_id
        start_label = task_name(tasks_map[start_id]) or start_id
        end_label = task_name(tasks_map[end_id]) or end_id
        sub_name = refactor_cluster_subplaybook_name(
            parent_name,
            start_label,
            end_label,
            start_task_id=start_id,
            end_task_id=end_id,
        )
        sub = build_subplaybook_cluster(playbook, cluster_check, name=sub_name)
        jobs.append(
            {
                "kind": "cluster",
                "start_task_id": start_id,
                "end_task_id": end_id,
                "cluster_check": cluster_check,
                "subplaybook_name": sub_name,
                "sub": sub,
            }
        )

    for task_id, root_check in zip(task_ids, combined_check.root_checks):
        task_label = task_name(tasks_map[task_id]) or task_id
        sub_name = refactor_subplaybook_name(parent_name, task_label, task_id=task_id)
        sub = build_subplaybook(playbook, task_id, name=sub_name, root_check=root_check)
        jobs.append(
            {
                "kind": "root",
                "task_id": task_id,
                "root_check": root_check,
                "subplaybook_name": sub_name,
                "sub": sub,
            }
        )

    bind_by_id = creds.platform.value == "xsiam"
    script_names, playbook_names = _load_script_and_playbook_names(client, playbook, cache, sink)
    post_specs = list(getattr(args, "post_task_updates", None) or [])
    for index, job in enumerate(jobs, 1):
        prepared_sub, sub_prep = prepare_playbook_for_yaml_export(job["sub"], cache)
        job["sub"] = prepared_sub
        embed_sub_playbook_description_on_job(source=playbook, job=job, post_specs=post_specs)
        if sub_prep.get("unresolved_bindings"):
            sink.write_json(f"03-subplaybook-bindings-{index:02d}.json", sub_prep)
            sink.log(
                f"Warning: {len(sub_prep['unresolved_bindings'])} unresolved playbook binding(s) "
                f"in sub-playbook {index}"
            )
        sub_yaml = dumps_yaml(
            prepared_sub,
            policy=policy,
            script_names=script_names,
            playbook_names=playbook_names,
            bind_subplaybooks_by_id=bind_by_id,
        )
        job["sub_yaml"] = sub_yaml
        sink.write_json(f"03-subplaybook-built-{index:02d}.json", prepared_sub)
        sink.write_text(f"03-subplaybook-built-{index:02d}.yaml", sub_yaml)

    variant = "parallel" if getattr(args, "parallel", False) else "sequential"
    result: JsonDict = {
        "platform": creds.platform.value,
        "phase": "upload" if args.upload_only else "full",
        "execution_variant": variant,
        "source_playbook": {"id": playbook.get("id"), "name": playbook.get("name")},
        "task_ids": task_ids,
        "clusters": [item.to_dict() for item in combined_check.clusters],
        "multi_extract_check": combined_check.to_dict(),
        "parent_copy_name": parent_copy_name,
        "damp_run": {"enabled": bool(args.damp_run)},
        "extractions": [],
        "parent": None,
    }

    return ExtractMultiState(
        args=args,
        creds=creds,
        client=client,
        cache=cache,
        policy=policy,
        sink=sink,
        playbook=playbook,
        jobs=jobs,
        result=result,
        combined_check=combined_check,
        parent_copy_name=parent_copy_name,
        task_ids=task_ids,
        bind_by_id=bind_by_id,
        script_names=script_names,
        playbook_names=playbook_names,
        sub_ids=[None] * len(jobs),
        execution_variant=variant,
    )


def _compare_after_parent(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "compare_after_parent", False))


def _refresh_cache_with_log(state: ExtractMultiState, *, phase: str) -> Optional[int]:
    """Refresh playbook-utils cache; returns exit code on failure."""
    from .cli import _finish_extract

    args = state.args
    try:
        if state.creds.platform.value == "xsiam":
            state.sink.log(f"{phase}: Refreshing XSIAM search cache")
        else:
            state.sink.log(f"{phase}: Refreshing playbook cache")
        state.cache.refresh()
        state.cache_refreshed = True
    except Exception as exc:
        for entry in state.result.get("extractions") or []:
            if isinstance(entry, dict):
                entry["download_error"] = str(exc)
        return _finish_extract(
            args,
            state.client,
            state.cache,
            state.sink,
            state.result,
            exit_code=1,
            text=f"Cache refresh failed: {exc}",
        )
    return None


def compare_subplaybooks_sequential(state: ExtractMultiState) -> None:
    """Run round-trip compares for all uploaded subs (shared by sequential and deferred paths)."""
    for index, (job, entry) in enumerate(zip(state.jobs, state.result["extractions"]), 1):
        _compare_one(state, index, job, entry)


def _new_extraction_entry(job: JsonDict) -> JsonDict:
    sub_name = str(job["subplaybook_name"])
    entry: JsonDict = {
        "kind": job["kind"],
        "subplaybook_name": sub_name,
        "uploaded_subplaybook": None,
        "compare": None,
        "download_error": None,
        "upload_error": None,
    }
    if job["kind"] == "cluster":
        entry["start_task_id"] = job["start_task_id"]
        entry["end_task_id"] = job["end_task_id"]
    else:
        entry["task_id"] = job["task_id"]
    return entry


def upload_compare_subplaybooks_sequential(state: ExtractMultiState) -> Optional[int]:
    """Upload subs sequentially, refresh cache once, compare sequentially. Returns exit code on failure."""
    from .cli import _finish_extract

    args = state.args
    if _compare_after_parent(args):
        state.sink.log(
            f"Phase 1/5: Create and upload refactored sub-playbooks ({len(state.jobs)} sequential upload(s))"
        )
    for index, job in enumerate(state.jobs, 1):
        sub_name = str(job["subplaybook_name"])
        entry = _new_extraction_entry(job)
        state.sink.log(f"Uploading sub-playbook {index}/{len(state.jobs)} {sub_name!r}")
        upload_response = state.client.save_yaml(
            yaml_for_sub_upload(state, job),
            filename=f"{slug(sub_name)}.yml",
        )
        state.cache.on_upload()
        state.sink.write_json(f"04-subplaybook-upload-{index:02d}.json", upload_response)
        failures = insert_failure_items(upload_response)
        already_exists = any("already exists" in str(item.get("error") or "").lower() for item in failures)
        if failures and not already_exists:
            entry["upload_error"] = failures
            state.result["extractions"].append(entry)
            label = job.get("task_id") or f"{job.get('start_task_id')}:{job.get('end_task_id')}"
            text = f"Sub-playbook upload failed for {label}:\n" + "\n".join(
                f"  {item.get('id')}: {item.get('error')}" for item in failures
            )
            return _finish_extract(args, state.client, state.cache, state.sink, state.result, exit_code=1, text=text)

        saved = unwrap_saved_playbook(upload_response) or {}
        saved_id = str(saved.get("id") or "")
        entry["uploaded_subplaybook"] = {
            "id": saved_id or None,
            "name": sub_name,
            "already_exists": already_exists,
        }
        if already_exists and not args.upload_only:
            state.sink.log(f"Sub-playbook already exists; will reload {sub_name!r} after batch cache refresh")
        state.result["extractions"].append(entry)

    if args.upload_only:
        return None

    defer = _compare_after_parent(args)
    refresh_exit = _refresh_cache_with_log(
        state,
        phase="Phase 2/5: Pause and refresh cache" if defer else "Refreshing playbook cache once before batch compare",
    )
    if refresh_exit is not None:
        return refresh_exit

    if defer:
        state.sink.log("Deferring sub-playbook compare until after parent upload (legacy --compare-after-parent)")
        return None

    state.sink.log("Phase 3/5: Comparing uploaded sub-playbooks and reporting issues")
    compare_subplaybooks_sequential(state)
    return None


def _compare_one(state: ExtractMultiState, index: int, job: JsonDict, entry: JsonDict) -> None:
    sub_name = str(entry.get("subplaybook_name") or "")
    try:
        downloaded = state.cache.resolve(sub_name, force=False)
    except Exception as exc:
        entry["download_error"] = str(exc)
        state.any_mismatch = True
        return
    state.sink.write_json(f"05-subplaybook-downloaded-{index:02d}.json", downloaded)
    entry["uploaded_subplaybook"] = {
        "id": downloaded.get("id"),
        "name": downloaded.get("name"),
    }
    state.sub_ids[index - 1] = str(downloaded.get("id") or "") or None
    if job["kind"] == "cluster":
        compared = compare_source_to_downloaded_cluster_subplaybook(
            state.playbook,
            job["cluster_check"],
            downloaded,
            policy=state.policy,
            cache=state.cache,
        )
        label = f"{job['start_task_id']}:{job['end_task_id']}"
    else:
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
    state.sink.write_json(f"06-compare-{index:02d}.json", compared.to_dict())
    state.sink.write_text(f"06-compare-{index:02d}.txt", compared.human_summary())
    entry["compare"] = {
        "equal": compared.equal,
        "diff_count": len(compared.diffs),
        "diff_counts": summarize_diff_paths(compared.diffs),
    }
    state.sink.log(format_compare_log_line(compared, label))
    if not compared.equal:
        state.any_mismatch = True


def finalize_extract_multi(state: ExtractMultiState, *, parallel_post_steps: bool = False) -> int:
    """Parent rewrite, optional post-updates/descriptions, parent upload."""
    from .cli import (
        _apply_refactor_descriptions,
        _finish_extract,
        _run_post_task_updates,
    )

    args = state.args
    if state.any_mismatch and args.require_match and not _compare_after_parent(args):
        return _finish_extract(
            args,
            state.client,
            state.cache,
            state.sink,
            state.result,
            exit_code=2,
            text="One or more sub-playbook round-trips did not match (require-match).",
        )

    if state.bind_by_id:
        if not state.cache_refreshed:
            state.sink.log("Refreshing cache to resolve uploaded sub-playbook IDs for parent")
            try:
                state.cache.refresh()
                state.cache_refreshed = True
            except Exception as exc:
                return _finish_extract(
                    args,
                    state.client,
                    state.cache,
                    state.sink,
                    state.result,
                    exit_code=1,
                    text=f"Cache refresh failed before parent rewrite: {exc}",
                )
        for index, job in enumerate(state.jobs):
            if state.sub_ids[index]:
                continue
            sub_name = str(job["subplaybook_name"])
            try:
                resolved = state.cache.resolve(sub_name, force=False)
            except Exception as exc:
                state.sink.log(f"Could not resolve sub-playbook id for {sub_name!r}: {exc}")
                continue
            state.sub_ids[index] = str(resolved.get("id") or "") or None

    combined_check = state.combined_check
    cluster_count = len(combined_check.clusters)
    jobs = state.jobs
    cluster_sub_names = [str(job["subplaybook_name"]) for job in jobs[:cluster_count]]
    cluster_sub_ids = state.sub_ids[:cluster_count] if state.bind_by_id else None
    root_sub_names = [str(job["subplaybook_name"]) for job in jobs[cluster_count:]]
    root_sub_ids = state.sub_ids[cluster_count:] if state.bind_by_id else None

    if cluster_count and state.task_ids:
        parent = rewrite_parent_combined(
            state.playbook,
            cluster_checks=combined_check.clusters,
            cluster_subplaybook_names=cluster_sub_names,
            cluster_subplaybook_ids=cluster_sub_ids,
            task_ids=state.task_ids,
            subplaybook_names=root_sub_names,
            subplaybook_ids=root_sub_ids,
            copy_name=state.parent_copy_name,
            padding=args.padding,
            root_checks=combined_check.root_checks,
        )
    elif cluster_count:
        current = state.playbook
        current_copy_id: Optional[str] = None
        extractions: list[JsonDict] = []
        for cluster_check, sub_name, sub_id in zip(
            combined_check.clusters, cluster_sub_names, cluster_sub_ids or [None] * cluster_count
        ):
            current = rewrite_parent_cluster(
                current,
                cluster_check,
                subplaybook_name=sub_name,
                subplaybook_id=sub_id,
                copy_name=state.parent_copy_name,
                copy_id=current_copy_id,
                padding=args.padding,
            )
            extractions.append(dict(current.get("_refactor") or {}))
            current_copy_id = str(current.get("id") or current_copy_id or "")
        current["_refactor"] = {"cluster_extractions": extractions}
        parent = current
    else:
        parent = rewrite_parent_multi(
            state.playbook,
            state.task_ids,
            subplaybook_names=root_sub_names,
            subplaybook_ids=root_sub_ids,
            copy_name=state.parent_copy_name,
            padding=args.padding,
            root_checks=combined_check.root_checks,
        )

    parent, parent_prep = prepare_playbook_for_yaml_export(parent, state.cache)
    if parent_prep.get("unresolved_bindings"):
        state.sink.write_json("09-parent-bindings.json", parent_prep)
        state.sink.log(
            f"Warning: {len(parent_prep['unresolved_bindings'])} unresolved playbook binding(s) in parent copy"
        )
    state.sink.write_json("09-parent-rewritten.json", parent)
    state.result["parent"] = parent.get("_refactor")
    state.result["parent"]["name"] = parent.get("name")
    state.result["parent"]["id"] = parent.get("id")

    should_upload_parent = args.upload_only or not state.any_mismatch or args.upload_parent_on_mismatch
    parent_uploaded = False

    parent_yaml = yaml_for_parent_upload(state, parent)
    state.sink.write_text("09-parent-rewritten.yaml", parent_yaml)

    if state.any_mismatch and not args.upload_parent_on_mismatch and not args.upload_only:
        state.sink.log("Mismatch: not uploading parent copy (pass --upload-parent-on-mismatch to override)")
    elif should_upload_parent and not args.upload_only:
        state.sink.log(f"Phase 4/5: Create and upload refactored main playbook {state.parent_copy_name!r}")
        parent_upload = state.client.save_yaml(parent_yaml, filename=f"{slug(state.parent_copy_name)}.yml")
        state.cache.on_upload()
        state.sink.write_json("10-parent-upload.json", parent_upload)
        state.result["parent"]["upload"] = parent_upload
        parent_uploaded = True

    refresh_after_parent = getattr(args, "refresh_after_parent_upload", True)
    if parent_uploaded and refresh_after_parent and not args.upload_only:
        refresh_exit = _refresh_cache_with_log(state, phase="Phase 5/5: Refresh cache after parent upload")
        if refresh_exit is not None:
            return refresh_exit

    if _compare_after_parent(args) and not args.upload_only and should_upload_parent and parent_uploaded:
        state.sink.log("Phase 5/5: Comparing uploaded sub-playbooks (legacy --compare-after-parent)")
        if parallel_post_steps:
            from .extract_multi_parallel import compare_subplaybooks_parallel

            compare_subplaybooks_parallel(state)
        else:
            compare_subplaybooks_sequential(state)

    can_post_steps = not args.upload_only and not state.any_mismatch

    post_result: Optional[JsonDict] = None
    post_ok = True
    if args.post_task_updates and can_post_steps:
        sub_names = [str(job["subplaybook_name"]) for job in jobs]
        state.sink.log(f"Running post-task updates on {len(sub_names)} generated sub-playbook(s)")
        if parallel_post_steps:
            from .extract_multi_parallel import run_post_task_updates_parallel

            post_result = run_post_task_updates_parallel(
                client=state.client,
                cache=state.cache,
                policy=state.policy,
                playbook_names=sub_names,
                post_specs=args.post_task_updates,
                sink=state.sink,
                args=args,
            )
        else:
            post_result = _run_post_task_updates(
                client=state.client,
                cache=state.cache,
                policy=state.policy,
                playbook_names=sub_names,
                post_specs=args.post_task_updates,
                sink=state.sink,
            )
        state.result["post_task_updates"] = post_result
        state.sink.write_json("11-post-task-updates.json", post_result)
        post_ok = bool(post_result.get("ok"))
    elif args.post_task_updates and not can_post_steps:
        state.sink.log("Skipping post-task updates (requires successful sub-playbook compare)")

    description_ok = True
    if can_post_steps:
        state.sink.log("Applying refactor description to parent copy (subs set on first upload)")
        if parallel_post_steps:
            from .extract_multi_parallel import apply_refactor_descriptions_parallel

            parent, description_result = apply_refactor_descriptions_parallel(
                client=state.client,
                cache=state.cache,
                policy=state.policy,
                sink=state.sink,
                source=state.playbook,
                parent=parent,
                post_result=post_result,
                post_specs=args.post_task_updates or [],
                args=args,
                skip_sub_uploads=True,
            )
        else:
            parent, description_result = _apply_refactor_descriptions(
                client=state.client,
                cache=state.cache,
                policy=state.policy,
                sink=state.sink,
                source=state.playbook,
                parent=parent,
                post_result=post_result,
                post_specs=args.post_task_updates or [],
                skip_sub_uploads=True,
            )
        state.result["refactor_descriptions"] = description_result
        description_ok = bool(description_result.get("ok"))

    equal_count = sum(1 for entry in state.result["extractions"] if (entry.get("compare") or {}).get("equal"))
    summary = (
        f"Multi-extract ({state.execution_variant}): {cluster_count} cluster(s), {len(state.task_ids)} root task(s), "
        f"equal={equal_count}/{len(state.result['extractions']) if not args.upload_only else 'n/a'}"
    )
    exit_code = 2 if state.any_mismatch else 0
    if args.post_task_updates and can_post_steps:
        applied = sum(1 for row in (post_result or {}).get("outcomes", []) if not row.get("skipped"))
        summary += f"; post-updates={applied}/{len(jobs)} ok={post_ok}"
        if not post_ok:
            exit_code = 2
    if can_post_steps:
        summary += f"; descriptions ok={description_ok}"
        if not description_ok:
            exit_code = 2

    if args.upload_only:
        return _finish_extract(args, state.client, state.cache, state.sink, state.result, exit_code=0, text=summary + " (upload-only)")
    return _finish_extract(args, state.client, state.cache, state.sink, state.result, exit_code=exit_code, text=summary)
