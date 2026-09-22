"""Apply task updates and overwrite a playbook in place."""

from __future__ import annotations

import copy
from typing import List, Mapping, Optional, Sequence

from .cache import PlaybookCache
from .client import PlaybookClient
from .context_sharing import (
    TaskContextUpdate,
    apply_playbook_context_updates,
    preflight_context_updates,
    read_task_context_state,
    validate_task_context_states,
)
from .debugio import DebugSink, slug
from .error_retry import (
    TaskErrorUpdate,
    apply_playbook_error_updates,
    parse_update_spec,
    preflight_error_updates,
    read_task_error_state,
    validate_task_states,
)
from .fields import FieldPolicy
from .keys import JsonDict, playbook_tasks
from .task_match import TaskNameMatch, find_matching_regular_script_task_ids
from .yaml_codec import dumps_yaml


def expand_error_updates_from_matches(
    playbook: Mapping[str, object],
    matches: Sequence[TaskNameMatch],
    actions: str,
) -> tuple[List[TaskErrorUpdate], List[JsonDict]]:
    """Build per-task error updates for every regular script task matching ``matches``."""
    task_ids = find_matching_regular_script_task_ids(playbook, matches)
    if not task_ids:
        return [], []
    template = parse_update_spec(f"_:{actions}")
    updates = [
        TaskErrorUpdate(
            task_id=tid,
            clear_retry=template.clear_retry,
            retry_count=template.retry_count,
            retry_interval=template.retry_interval,
            error_handling=template.error_handling,
        )
        for tid in task_ids
    ]
    return preflight_error_updates(playbook, updates)


def overwrite_playbook_description(
    *,
    client: PlaybookClient,
    cache: PlaybookCache,
    policy: FieldPolicy,
    playbook: Mapping[str, object],
    description: str,
    sink: Optional[DebugSink] = None,
) -> JsonDict:
    """Overwrite only the playbook-level description via save/yaml."""
    playbook_id = str(playbook.get("id") or "")
    playbook_name = str(playbook.get("name") or playbook_id)
    modified = copy.deepcopy(dict(playbook))
    modified["description"] = description
    modified.pop("comment", None)

    if sink:
        sink.log(f"Uploading description overwrite for {playbook_name!r} ({playbook_id})")

    yaml_text = dumps_yaml(
        modified,
        policy=policy,
        script_names=client.script_id_to_name(),
        overwrite=True,
    )
    upload = client.save_yaml(yaml_text, filename=f"{slug(playbook_name)}.yml")
    cache.invalidate()
    cache.refresh()
    downloaded = cache.resolve(playbook_id or playbook_name, force=True)
    downloaded_description = str(downloaded.get("description") or downloaded.get("comment") or "")
    ok = downloaded_description.strip() == description.strip()
    return {
        "playbook_id": playbook_id,
        "playbook_name": playbook_name,
        "ok": ok,
        "description_length": len(description),
        "upload": upload,
    }


def _validate_uploaded_task_updates(
    *,
    cache: PlaybookCache,
    playbook_id: str,
    playbook_name: str,
    before_error: Mapping[str, object],
    before_context: Mapping[str, object],
    expected_error: Mapping[str, object],
    expected_context: Mapping[str, object],
    error_update_ids: set[str],
    context_update_ids: set[str],
    error_rejected: Sequence[JsonDict],
    context_rejected: Sequence[JsonDict],
) -> JsonDict:
    downloaded = cache.resolve(playbook_id or playbook_name, force=True)
    dl_tasks = playbook_tasks(downloaded)
    after_error = {tid: read_task_error_state(dl_tasks[tid], tid) for tid in before_error}
    after_context = {tid: read_task_context_state(dl_tasks[tid], tid) for tid in before_context}
    error_mismatches = validate_task_states(downloaded, expected_error) if expected_error else []
    context_mismatches = (
        validate_task_context_states(downloaded, expected_context) if expected_context else []
    )
    unchanged_error_drift = [
        tid
        for tid in before_error
        if tid not in error_update_ids and after_error[tid] != before_error[tid]
    ]
    unchanged_context_drift = [
        tid
        for tid in before_context
        if tid not in context_update_ids and after_context[tid] != before_context[tid]
    ]
    ok = (
        not error_rejected
        and not context_rejected
        and not error_mismatches
        and not context_mismatches
        and not unchanged_error_drift
        and not unchanged_context_drift
    )
    return {
        "ok": ok,
        "after_error": {tid: after_error[tid].to_dict() for tid in after_error},
        "after_context": {tid: after_context[tid].to_dict() for tid in after_context},
        "error_mismatches": error_mismatches,
        "context_mismatches": context_mismatches,
        "unchanged_error_drift": unchanged_error_drift,
        "unchanged_context_drift": unchanged_context_drift,
    }


def overwrite_playbook_task_updates(
    *,
    client: PlaybookClient,
    cache: PlaybookCache,
    policy: FieldPolicy,
    playbook: Mapping[str, object],
    error_updates: Sequence[TaskErrorUpdate],
    context_updates: Sequence[TaskContextUpdate],
    sink: Optional[DebugSink] = None,
    dry_run: bool = False,
    defer_cache_refresh: bool = False,
) -> JsonDict:
    """Apply updates and overwrite the playbook via save/yaml. Returns an outcome dict."""
    playbook_id = str(playbook.get("id") or "")
    playbook_name = str(playbook.get("name") or playbook_id)
    tasks = playbook_tasks(playbook)

    error_updates_list, error_rejected = preflight_error_updates(playbook, list(error_updates))
    context_updates_list, context_rejected = preflight_context_updates(playbook, list(context_updates))

    error_update_ids = {update.task_id for update in error_updates_list}
    context_update_ids = {update.task_id for update in context_updates_list}
    validate_ids = sorted(error_update_ids | context_update_ids)

    before_error = {
        tid: read_task_error_state(tasks[tid], tid) for tid in validate_ids if tid in tasks
    }
    before_context = {
        tid: read_task_context_state(tasks[tid], tid) for tid in validate_ids if tid in tasks
    }

    modified = copy.deepcopy(dict(playbook))
    if error_updates_list:
        modified = apply_playbook_error_updates(modified, error_updates_list)
    if context_updates_list:
        modified = apply_playbook_context_updates(modified, context_updates_list)

    has_changes = bool(error_updates_list or context_updates_list)
    expected_error = dict(before_error)
    for update in error_updates_list:
        node = copy.deepcopy(modified["tasks"][update.task_id])
        expected_error[update.task_id] = read_task_error_state(node, update.task_id)
    expected_context = dict(before_context)
    for update in context_updates_list:
        node = copy.deepcopy(modified["tasks"][update.task_id])
        expected_context[update.task_id] = read_task_context_state(node, update.task_id)

    if dry_run or not has_changes:
        return {
            "playbook_id": playbook_id,
            "playbook_name": playbook_name,
            "dry_run": dry_run,
            "ok": not error_rejected and not context_rejected and has_changes,
            "error_updates": [update.to_dict() for update in error_updates_list],
            "context_updates": [update.to_dict() for update in context_updates_list],
            "error_rejected": error_rejected,
            "context_rejected": context_rejected,
            "before_error": {tid: before_error[tid].to_dict() for tid in before_error},
            "expected_error": {tid: expected_error[tid].to_dict() for tid in expected_error},
            "before_context": {tid: before_context[tid].to_dict() for tid in before_context},
            "expected_context": {tid: expected_context[tid].to_dict() for tid in expected_context},
        }

    if sink:
        sink.log(f"Uploading overwrite for {playbook_name!r} ({playbook_id})")

    yaml_text = dumps_yaml(
        modified,
        policy=policy,
        script_names=client.script_id_to_name(),
        overwrite=True,
    )
    upload = client.save_yaml(yaml_text, filename=f"{slug(playbook_name)}.yml")
    base_payload = {
        "playbook_id": playbook_id,
        "playbook_name": playbook_name,
        "error_updates": [update.to_dict() for update in error_updates_list],
        "context_updates": [update.to_dict() for update in context_updates_list],
        "error_rejected": error_rejected,
        "context_rejected": context_rejected,
        "before_error": {tid: before_error[tid].to_dict() for tid in before_error},
        "before_context": {tid: before_context[tid].to_dict() for tid in before_context},
        "expected_error": {tid: expected_error[tid].to_dict() for tid in expected_error},
        "expected_context": {tid: expected_context[tid].to_dict() for tid in expected_context},
        "error_update_ids": sorted(error_update_ids),
        "context_update_ids": sorted(context_update_ids),
        "upload": upload,
    }
    if defer_cache_refresh:
        base_payload["validation_deferred"] = True
        base_payload["ok"] = not error_rejected and not context_rejected
        base_payload["_validation_ctx"] = {
            "playbook_id": playbook_id,
            "playbook_name": playbook_name,
            "before_error": before_error,
            "before_context": before_context,
            "expected_error": expected_error,
            "expected_context": expected_context,
            "error_update_ids": error_update_ids,
            "context_update_ids": context_update_ids,
            "error_rejected": error_rejected,
            "context_rejected": context_rejected,
        }
        return base_payload

    cache.invalidate()
    cache.refresh()
    validated = _validate_uploaded_task_updates(
        cache=cache,
        playbook_id=playbook_id,
        playbook_name=playbook_name,
        before_error=before_error,
        before_context=before_context,
        expected_error=expected_error,
        expected_context=expected_context,
        error_update_ids=error_update_ids,
        context_update_ids=context_update_ids,
        error_rejected=error_rejected,
        context_rejected=context_rejected,
    )
    return {**base_payload, **validated}

