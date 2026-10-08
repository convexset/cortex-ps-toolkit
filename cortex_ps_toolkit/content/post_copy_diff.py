"""Optional post-copy fidelity diff (source document vs target read-back).

Uses ``content.representation`` normalization (copy-fidelity probes), not
playbook-utils refactor compare (``normalize_playbook``, ``canonicalize_extract_tasks``,
``normalize_playbook_call_ids_for_compare``). Refactor compare is subgraph- and
cache-binding-aware; post-copy diff compares full documents with cross-tenant
ignore rules (e.g. strips ``playbookId`` when ``playbookName`` is present).
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Mapping

from .. import __version__
from ..core.client import TenantApiError
from ..credentials import CredentialProfile
from ..ops_log import op_info
from .representation import ContentKind, diff_representations_classified

FetchDoc = Callable[[CredentialProfile, str], Mapping[str, Any]]

# Bump when normalization / ignore rules change (surfaced in API + UI telemetry).
# v4: benign tasks.*.task.playbookName null → set (post deep-copy binding).
POST_COPY_DIFF_PROBE_ID = "cptk.repr-copy-fidelity/v4"

COMPARE_MODE = "source_pre_upload_snapshot_vs_target_get_after_save"

NOTE_UPLOAD_OK_DIFF_ERROR = (
    "TELEM: tenant save reported success; diff error is read-back/id/cache/compare — "
    "not necessarily a failed upload."
)
NOTE_UPLOAD_OK_MISMATCH = (
    "TELEM: tenant save reported success; mismatch is normalized representation compare only "
    "(tenant may rewrite metadata, IDs, or playbook refs)."
)


def _doc_fingerprint(document: Mapping[str, Any], kind: ContentKind) -> str:
    if kind == "playbook":
        tasks = document.get("tasks")
        task_count = len(tasks) if isinstance(tasks, dict) else "?"
        return f"pb:tasks={task_count}"
    if kind == "script":
        body = document.get("script") or document.get("code") or ""
        return f"sc:script_len={len(str(body))}"
    if kind == "list":
        data = document.get("data")
        if isinstance(data, list):
            return f"list:rows={len(data)}"
        return "list:rows=?"
    return f"doc:keys={len(document)}"


def _error_code_for_fetch(exc: BaseException) -> str:
    if isinstance(exc, TenantApiError):
        return f"READ_BACK_HTTP_{exc.status_code or 'ERR'}"
    return "READ_BACK_FETCH_FAILED"


def _attach_row_telemetry(
    payload: dict[str, Any],
    *,
    row: Mapping[str, Any],
    kind: ContentKind,
    source_entity_id: str,
    target_entity_id: str,
) -> dict[str, Any]:
    upload_status = str(row.get("status") or "")
    binding_unresolved = row.get("binding_unresolved")
    unresolved_count = len(binding_unresolved) if isinstance(binding_unresolved, list) else 0
    payload["upload_status"] = upload_status or None
    payload["source_entity_id"] = source_entity_id or None
    payload["target_entity_id"] = target_entity_id or None
    payload["binding_unresolved_count"] = unresolved_count
    payload["status_code"] = row.get("status_code")
    if upload_status in ("copied", "updated"):
        if payload.get("error"):
            payload["telemetry_note"] = NOTE_UPLOAD_OK_DIFF_ERROR
        elif payload.get("outcome") == "mismatch":
            payload["telemetry_note"] = NOTE_UPLOAD_OK_MISMATCH
        elif payload.get("outcome") == "match_ignored_delta":
            payload["telemetry_note"] = (
                "TELEM: upload OK; ignored-only deltas (tenant metadata) — see post_copy_diff.ignored."
            )
    return payload


def post_copy_diff_payload(
    *,
    source_doc: Mapping[str, Any],
    target: CredentialProfile,
    target_entity_id: str,
    kind: ContentKind,
    fetch: FetchDoc,
    item_name: str,
) -> dict[str, Any]:
    """Compare normalized source doc to tenant read-back after copy/update."""
    entity_id = str(target_entity_id or "").strip()
    base: dict[str, Any] = {
        "probe": POST_COPY_DIFF_PROBE_ID,
        "compare_mode": COMPARE_MODE,
        "kind": kind,
        "target_profile": target.slug,
        "item_name": item_name,
        "source_fingerprint": _doc_fingerprint(source_doc, kind),
        "read_back_id": entity_id or None,
    }
    if not entity_id:
        return {
            **base,
            "equal": False,
            "flagged": [],
            "ignored": [],
            "differences": [],
            "flagged_count": 0,
            "ignored_count": 0,
            "outcome": "error",
            "error": "missing target id for read-back",
            "error_code": "MISSING_TARGET_ID",
        }
    try:
        read_back = fetch(target, entity_id)
    except (TenantApiError, KeyError, RuntimeError) as exc:
        return {
            **base,
            "equal": False,
            "flagged": [],
            "ignored": [],
            "differences": [],
            "flagged_count": 0,
            "ignored_count": 0,
            "outcome": "error",
            "error": str(exc),
            "error_code": _error_code_for_fetch(exc),
            "read_back_fingerprint": None,
        }
    read_back_name = read_back.get("name") if isinstance(read_back, Mapping) else None
    base["read_back_name"] = str(read_back_name) if read_back_name else None
    base["read_back_fingerprint"] = _doc_fingerprint(read_back, kind)

    classified = diff_representations_classified(source_doc, read_back, kind)
    payload = classified.to_dict()
    payload.update(base)
    flagged = payload.get("flagged") or []
    ignored = payload.get("ignored") or []
    payload["difference_count"] = len(flagged)
    payload["ignored_delta_count"] = len(ignored)
    sample_paths = [row.get("path") for row in flagged[:8] if row.get("path")]
    if sample_paths:
        payload["sample_paths"] = sample_paths
    if flagged:
        payload["first_delta"] = flagged[0]
    elif ignored:
        payload["first_ignored_delta"] = ignored[0]

    if payload.get("error"):
        payload["outcome"] = "error"
    elif classified.equal and not ignored:
        payload["outcome"] = "match"
    elif classified.equal and ignored:
        payload["outcome"] = "match_ignored_delta"
    else:
        payload["outcome"] = "mismatch"
        sample_paths_log = ", ".join(str(path) for path in sample_paths[:5])
        suffix = f" (e.g. {sample_paths_log})" if sample_paths_log else ""
        op_info(
            "Post-copy diff: %s %r on %s flagged %d ignored %d delta(s)%s",
            kind,
            item_name,
            target.slug,
            len(flagged),
            len(ignored),
            suffix,
        )
    return payload


def apply_post_copy_diffs(
    results: list[dict[str, Any]],
    *,
    target: CredentialProfile,
    kind: ContentKind,
    fetch: FetchDoc,
    pending: list[tuple[int, Mapping[str, Any], str]],
) -> dict[str, Any]:
    """Attach post_copy_diff to result rows; pending is (result_index, source_doc, name)."""
    matched = 0
    mismatched = 0
    errors = 0
    ignored_only = 0
    upload_ok_with_diff_issue = 0
    for index, source_doc, name in pending:
        row = results[index]
        source_entity_id = str(
            row.get("playbook_id")
            or row.get("script_id")
            or row.get("list_id")
            or row.get("id")
            or row.get("source_id")
            or ""
        )
        target_id = str(
            row.get("target_playbook_id")
            or row.get("target_script_id")
            or row.get("target_id")
            or ""
        )
        payload = post_copy_diff_payload(
            source_doc=source_doc,
            target=target,
            target_entity_id=target_id,
            kind=kind,
            fetch=fetch,
            item_name=name,
        )
        payload = _attach_row_telemetry(
            payload,
            row=row,
            kind=kind,
            source_entity_id=source_entity_id,
            target_entity_id=target_id,
        )
        row["post_copy_diff"] = payload
        if payload.get("error"):
            errors += 1
        elif payload.get("outcome") == "mismatch":
            mismatched += 1
        elif payload.get("outcome") == "match_ignored_delta":
            ignored_only += 1
            matched += 1
        elif payload.get("equal"):
            matched += 1
        else:
            mismatched += 1
        if row.get("status") in ("copied", "updated") and payload.get("outcome") in (
            "error",
            "mismatch",
            "match_ignored_delta",
        ):
            upload_ok_with_diff_issue += 1
    counts = {
        "matched": matched,
        "mismatched": mismatched,
        "errors": errors,
        "ignored_only": ignored_only,
    }
    return {
        **counts,
        "probe": POST_COPY_DIFF_PROBE_ID,
        "compare_mode": COMPARE_MODE,
        "upload_ok_with_diff_issue": upload_ok_with_diff_issue,
    }


def _empty_diff_summary() -> dict[str, int]:
    return {"matched": 0, "mismatched": 0, "errors": 0, "ignored_only": 0}


def merge_diff_summaries(*summaries: Mapping[str, int]) -> dict[str, int]:
    out = _empty_diff_summary()
    for summary in summaries:
        for key in out:
            out[key] += int(summary.get(key) or 0)
    return out


def aggregate_copy_diff_report(copy_result: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten per-row post_copy_diff blocks from any copy response shape."""
    rows: list[dict[str, Any]] = []
    for key in ("results", "script_results", "playbook_results"):
        for row in copy_result.get(key) or []:
            diff = row.get("post_copy_diff")
            if not diff:
                continue
            rows.append({
                "name": row.get("name")
                or row.get("item_name")
                or row.get("target_name")
                or row.get("list_id")
                or row.get("playbook_id")
                or row.get("script_id")
                or "?",
                "status": row.get("status"),
                "kind": diff.get("kind"),
                "outcome": diff.get("outcome"),
                "post_copy_diff": diff,
            })
    flagged_total = sum(int((row["post_copy_diff"].get("flagged_count") or 0)) for row in rows)
    ignored_total = sum(int((row["post_copy_diff"].get("ignored_count") or 0)) for row in rows)
    return {
        "probe": copy_result.get("post_copy_diff_summary", {}).get("probe")
        or copy_result.get("telemetry", {}).get("post_copy_diff_probe"),
        "row_count": len(rows),
        "flagged_delta_total": flagged_total,
        "ignored_delta_total": ignored_total,
        "rows": rows,
    }


def apply_deep_copy_post_diffs(
    *,
    source: CredentialProfile,
    target: CredentialProfile,
    script_results: list[dict[str, Any]],
    playbook_results: list[dict[str, Any]],
    playbook_source_docs: Mapping[str, Mapping[str, Any]],
    fetch_script: FetchDoc,
    fetch_playbook: FetchDoc,
) -> dict[str, Any]:
    """Post-copy diff for deep (component) copy script + playbook result rows."""
    script_pending: list[tuple[int, Mapping[str, Any], str]] = []
    for index, row in enumerate(script_results):
        if row.get("status") not in ("copied", "updated"):
            continue
        script_id = str(row.get("script_id") or "")
        if not script_id:
            continue
        script_pending.append((index, fetch_script(source, script_id), str(row.get("name") or script_id)))

    playbook_pending: list[tuple[int, Mapping[str, Any], str]] = []
    for index, row in enumerate(playbook_results):
        if row.get("status") not in ("copied", "updated"):
            continue
        playbook_id = str(row.get("playbook_id") or "")
        if not playbook_id:
            continue
        source_doc = playbook_source_docs.get(playbook_id)
        if source_doc is None:
            source_doc = fetch_playbook(source, playbook_id)
        playbook_pending.append((index, source_doc, str(row.get("name") or playbook_id)))

    script_summary = (
        apply_post_copy_diffs(
            script_results,
            target=target,
            kind="script",
            fetch=fetch_script,
            pending=script_pending,
        )
        if script_pending
        else {**_empty_diff_summary(), "probe": POST_COPY_DIFF_PROBE_ID, "compare_mode": COMPARE_MODE, "upload_ok_with_diff_issue": 0}
    )
    playbook_summary = (
        apply_post_copy_diffs(
            playbook_results,
            target=target,
            kind="playbook",
            fetch=fetch_playbook,
            pending=playbook_pending,
        )
        if playbook_pending
        else {**_empty_diff_summary(), "probe": POST_COPY_DIFF_PROBE_ID, "compare_mode": COMPARE_MODE, "upload_ok_with_diff_issue": 0}
    )
    total_counts = merge_diff_summaries(script_summary, playbook_summary)
    upload_ok_with_diff_issue = int(script_summary.get("upload_ok_with_diff_issue") or 0) + int(
        playbook_summary.get("upload_ok_with_diff_issue") or 0
    )
    return {
        "scripts": script_summary,
        "playbooks": playbook_summary,
        "total": total_counts,
        "probe": POST_COPY_DIFF_PROBE_ID,
        "compare_mode": COMPARE_MODE,
        "upload_ok_with_diff_issue": upload_ok_with_diff_issue,
        "interpretation": (
            "post_copy_diff compares normalized source snapshot to GET-after-save on target; "
            "upload_ok_with_diff_issue counts saved rows where probe still reported mismatch/error."
        ),
    }


def new_copy_run_telemetry(*, operation: str, post_copy_diff: bool) -> dict[str, Any]:
    """Opaque run header for copy/deep-copy API responses (debugging)."""
    return {
        "run_id": uuid.uuid4().hex[:12],
        "operation": operation,
        "toolkit_version": __version__,
        "post_copy_diff_enabled": bool(post_copy_diff),
        "post_copy_diff_probe": POST_COPY_DIFF_PROBE_ID if post_copy_diff else None,
        "compare_mode": COMPARE_MODE if post_copy_diff else None,
    }
