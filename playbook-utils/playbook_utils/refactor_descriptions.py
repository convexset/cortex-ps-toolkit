"""Build playbook-level descriptions for refactor parent and sub-playbooks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Mapping, Optional, Sequence

from .error_retry import parse_update_spec
from .keys import JsonDict
from .task_match import parse_post_task_update_spec


@dataclass(frozen=True)
class HttpV2TaskRef:
    task_id: str
    subplaybook_name: str
    retry_count: Optional[int] = None
    retry_interval: Optional[int] = None


def source_playbook_description(source: Mapping[str, object]) -> str:
    """Resolve the source playbook description from ``description`` or legacy ``comment``."""
    description = source.get("description")
    if description is not None and str(description).strip():
        return str(description).strip()
    comment = source.get("comment")
    if comment is not None and str(comment).strip():
        return str(comment).strip()
    return ""


def sort_task_ids(task_ids: Sequence[str]) -> List[str]:
    def sort_key(task_id: str) -> tuple[int, int | str]:
        if task_id.isdigit():
            return (0, int(task_id))
        return (1, task_id)

    return sorted((str(task_id) for task_id in task_ids), key=sort_key)


def collect_extraction_metas(refactor: Mapping[str, object]) -> List[JsonDict]:
    """Flatten per-extraction metadata stored on a rewritten parent playbook."""
    metas: List[JsonDict] = []
    for key in ("cluster_extractions", "extractions"):
        chunk = refactor.get(key)
        if isinstance(chunk, list):
            metas.extend(dict(item) for item in chunk if isinstance(item, Mapping))
    kind = refactor.get("kind")
    if kind in ("root", "cluster"):
        metas.append(dict(refactor))
    return metas


def aspect_line(meta: Mapping[str, object]) -> str:
    sub_name = str(meta.get("subplaybook_name") or "")
    removed = sort_task_ids(meta.get("removed_task_ids") or [])
    moved = ", ".join(removed)
    if meta.get("kind") == "cluster":
        start_id = meta.get("start_task_id")
        end_id = meta.get("end_task_id")
        return (
            f" - Cluster Refactor from Task {start_id} to Task {end_id} into {sub_name}. "
            f"Tasks Moved: {moved}"
        )
    original_task_id = meta.get("original_task_id")
    return f" - Leaf Refactor from Task {original_task_id} into {sub_name}. Tasks Moved: {moved}"


def metrics_line(meta: Mapping[str, object]) -> str:
    sub_name = str(meta.get("subplaybook_name") or "")
    nodes = len(meta.get("removed_task_ids") or [])
    incoming = int(meta.get("incoming_replacements") or 0)
    outgoing = len(meta.get("end_outgoing") or [])
    return (
        f" - {sub_name}: {nodes} nodes moved to sub-playbook; "
        f"1 sub-playbook call node added to parent; "
        f"{incoming} incoming links re-written, {outgoing} outgoing links re-written"
    )


def refactor_totals(metas: Sequence[Mapping[str, object]]) -> JsonDict:
    return {
        "nodes": sum(len(meta.get("removed_task_ids") or []) for meta in metas),
        "calls": len(metas),
        "incoming": sum(int(meta.get("incoming_replacements") or 0) for meta in metas),
        "outgoing": sum(len(meta.get("end_outgoing") or []) for meta in metas),
    }


def totals_metrics_line(metas: Sequence[Mapping[str, object]]) -> str:
    totals = refactor_totals(metas)
    return (
        f" - Totals: {totals['nodes']} nodes moved; {totals['calls']} call nodes added; "
        f"{totals['incoming']} incoming links re-written, {totals['outgoing']} outgoing links re-written"
    )


def build_refactor_metrics_description(metas: Sequence[Mapping[str, object]]) -> List[str]:
    """Compact totals-only metrics for the uploaded parent description."""
    if not metas:
        return []
    totals = refactor_totals(metas)
    return [
        "Refactor Metrics:",
        f" - {totals['nodes']} nodes moved",
        f" - {totals['calls']} call nodes added",
        f" - {totals['incoming']} incoming links re-written",
        f" - {totals['outgoing']} outgoing links re-written",
    ]


def parse_httpv2_retry_from_specs(post_specs: Sequence[str]) -> tuple[Optional[int], Optional[int]]:
    for spec in post_specs:
        _, actions = parse_post_task_update_spec(spec)
        template = parse_update_spec(f"_:{actions}")
        if template.retry_count is not None:
            return template.retry_count, template.retry_interval
    return None, None


def httpv2_refs_from_post_specs_on_playbook(
    playbook: Mapping[str, object],
    *,
    subplaybook_name: str,
    post_specs: Sequence[str],
) -> List[HttpV2TaskRef]:
    """Predict HttpV2 description lines from post-task specs (same tasks as post-update would touch)."""
    from .playbook_update import expand_error_updates_from_matches
    from .task_match import parse_post_task_update_spec

    refs: List[HttpV2TaskRef] = []
    seen: set[str] = set()
    for spec in post_specs:
        match, actions = parse_post_task_update_spec(spec)
        expanded, _rejected = expand_error_updates_from_matches(playbook, [match], actions)
        for update in expanded:
            if update.retry_count is None or update.retry_interval is None:
                continue
            task_id = str(update.task_id)
            if not task_id or task_id in seen:
                continue
            seen.add(task_id)
            refs.append(
                HttpV2TaskRef(
                    task_id=task_id,
                    subplaybook_name=subplaybook_name,
                    retry_count=int(update.retry_count),
                    retry_interval=int(update.retry_interval),
                )
            )
    return refs


def extraction_meta_for_sub_job(sub: Mapping[str, object], subplaybook_name: str) -> JsonDict:
    meta = dict(sub.get("_refactor") or {})
    if not meta.get("subplaybook_name"):
        meta["subplaybook_name"] = subplaybook_name
    return meta


def embed_sub_playbook_description_on_job(
    *,
    source: Mapping[str, object],
    job: Mapping[str, object],
    post_specs: Sequence[str],
) -> str:
    """Set playbook-level ``description`` on a built sub-playbook before the first YAML upload."""
    sub = job.get("sub")
    if not isinstance(sub, dict):
        return ""
    sub_name = str(job.get("subplaybook_name") or "")
    meta = extraction_meta_for_sub_job(sub, sub_name)
    httpv2_refs = (
        httpv2_refs_from_post_specs_on_playbook(sub, subplaybook_name=sub_name, post_specs=post_specs)
        if post_specs
        else []
    )
    description = build_sub_description(
        source_name=str(source.get("name") or "playbook"),
        meta=meta,
        httpv2_refs=httpv2_refs,
        post_specs=post_specs,
    )
    sub["description"] = description
    sub.pop("comment", None)
    return description


def httpv2_refs_from_post_result(post_result: Optional[Mapping[str, object]]) -> List[HttpV2TaskRef]:
    refs: List[HttpV2TaskRef] = []
    if not post_result:
        return refs
    seen: set[str] = set()
    for outcome in post_result.get("outcomes") or []:
        if not isinstance(outcome, Mapping):
            continue
        if outcome.get("skipped") or not outcome.get("ok"):
            continue
        sub_name = str(outcome.get("playbook_name") or "")
        for update in outcome.get("error_updates") or []:
            if not isinstance(update, Mapping):
                continue
            retry_count = update.get("retry_count")
            retry_interval = update.get("retry_interval")
            if retry_count is None or retry_interval is None:
                continue
            task_id = str(update.get("task_id") or "")
            if not task_id or task_id in seen:
                continue
            seen.add(task_id)
            refs.append(
                HttpV2TaskRef(
                    task_id=task_id,
                    subplaybook_name=sub_name,
                    retry_count=int(retry_count),
                    retry_interval=int(retry_interval),
                )
            )
    return refs


def _httpv2_header_line(
    refs: Sequence[HttpV2TaskRef],
    post_specs: Sequence[str],
) -> str:
    retry_count = refs[0].retry_count if refs else None
    retry_interval = refs[0].retry_interval if refs else None
    if retry_count is None or retry_interval is None:
        retry_count, retry_interval = parse_httpv2_retry_from_specs(post_specs)
    if retry_count is None or retry_interval is None:
        return " - HTTPv2 Task On Error Configuration Set"
    return (
        f" - HTTPv2 Task On Error Configuration Set: Up to {retry_count} retries "
        f"with retry interval {retry_interval} seconds"
    )


def build_parent_description(
    *,
    source_name: str,
    source_description: str,
    metas: Sequence[Mapping[str, object]],
    httpv2_refs: Sequence[HttpV2TaskRef],
    post_specs: Sequence[str] = (),
) -> str:
    lines: List[str] = []
    if source_description:
        lines.extend([source_description, "", "---", ""])
    lines.append(f"Automatic Refactor of {source_name}:")
    for meta in metas:
        lines.append(aspect_line(meta))
    if httpv2_refs:
        lines.append(_httpv2_header_line(httpv2_refs, post_specs))
        for ref in sorted(httpv2_refs, key=lambda item: sort_task_ids([item.task_id])[0]):
            sub_suffix = f" ({ref.subplaybook_name})" if ref.subplaybook_name else ""
            lines.append(f"    * Task {ref.task_id}{sub_suffix}")
    if metas:
        lines.append("")
        lines.extend(build_refactor_metrics_description(metas))
    return "\n".join(lines)


def build_refactor_metrics_log(
    *,
    source_name: str,
    metas: Sequence[Mapping[str, object]],
) -> str:
    """Build refactor metrics text for debug output (not uploaded to the tenant)."""
    lines = [f"Refactor Metrics for {source_name}:"]
    for meta in metas:
        lines.append(metrics_line(meta))
    if metas:
        lines.append(totals_metrics_line(metas))
    return "\n".join(lines)


def build_sub_description(
    *,
    source_name: str,
    meta: Mapping[str, object],
    httpv2_refs: Sequence[HttpV2TaskRef],
    post_specs: Sequence[str] = (),
) -> str:
    sub_name = str(meta.get("subplaybook_name") or "")
    refs_for_sub = [ref for ref in httpv2_refs if ref.subplaybook_name == sub_name]
    lines = [f"Refactored from {source_name}", aspect_line(meta)]
    if refs_for_sub:
        lines.append(_httpv2_header_line(refs_for_sub, post_specs))
        for ref in sorted(refs_for_sub, key=lambda item: sort_task_ids([item.task_id])[0]):
            lines.append(f"    * Task {ref.task_id}")
    return "\n".join(lines)


def descriptions_for_refactor(
    *,
    source: Mapping[str, object],
    refactor: Mapping[str, object],
    post_result: Optional[Mapping[str, object]] = None,
    post_specs: Sequence[str] = (),
) -> JsonDict:
    """Return parent and per-sub description strings for a refactor result."""
    source_name = str(source.get("name") or "playbook")
    metas = collect_extraction_metas(refactor)
    httpv2_refs = httpv2_refs_from_post_result(post_result)
    parent_description = build_parent_description(
        source_name=source_name,
        source_description=source_playbook_description(source),
        metas=metas,
        httpv2_refs=httpv2_refs,
        post_specs=post_specs,
    )
    sub_descriptions = {
        str(meta.get("subplaybook_name") or ""): build_sub_description(
            source_name=source_name,
            meta=meta,
            httpv2_refs=httpv2_refs,
            post_specs=post_specs,
        )
        for meta in metas
        if meta.get("subplaybook_name")
    }
    return {
        "parent_description": parent_description,
        "sub_descriptions": sub_descriptions,
        "metrics_log": build_refactor_metrics_log(source_name=source_name, metas=metas),
        "extraction_count": len(metas),
        "httpv2_task_count": len(httpv2_refs),
    }
