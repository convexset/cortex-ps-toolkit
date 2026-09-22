"""Parallel tenant downloads of playbook/script bodies needed for analysis."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from ..credentials import CredentialProfile, get_profile
from ..ops_log import log_data_write, op_info
from ..scripts import api as scripts_api
from ..scripts.body_cache import load_script_body, save_script_body
from ..scripts.cache import find_script_in_index, script_index_maps
from ..settings import max_inflight_per_host
from . import api as playbooks_api
from .analysis_fetch_plan import plan_analysis_fetch_needs
from .cache import save_playbook_body
from .entity_resolution import resolve_automation_script
from .resolver import CachePlaybookResolver, ProgressCallback
from .yaml_helpers import iter_sub_playbook_refs, playbook_identity

_PLAYBOOK_FETCH_REASONS = frozenset({"missing_file", "modified_mismatch"})
_MAX_PLAN_ROUNDS = 64


def _parallel_workers(task_count: int) -> int:
    if task_count <= 0:
        return 1
    return max(1, min(max_inflight_per_host(), task_count))


def _fetch_playbook_row(
    profile: CredentialProfile,
    row: dict[str, str],
    *,
    on_progress: Optional[ProgressCallback],
    progress_lock: threading.Lock,
    counters: dict[str, int],
) -> dict[str, str]:
    pb_id = str(row.get("id") or "").strip()
    name = str(row.get("name") or pb_id)
    reason = str(row.get("reason") or "missing_file")
    if not pb_id:
        raise ValueError("playbook body fetch row missing id")

    with progress_lock:
        counters["current"] += 1
        current = counters["current"]
        total = counters["total"]
    if on_progress:
        on_progress(
            {
                "phase": "fetch_playbook",
                "status": "running",
                "playbook_id": pb_id,
                "playbook_name": name,
                "reason": reason,
                "current": current,
                "total": total,
            },
        )
    playbook = playbooks_api.get_playbook(profile, pb_id)
    store_id = str(playbook_identity(playbook)[0] or pb_id)
    path = save_playbook_body(profile, store_id, playbook)
    log_data_write("playbook body", detail=f"{name} ({store_id}) → {path}")
    if on_progress:
        on_progress(
            {
                "phase": "fetch_playbook",
                "status": "complete",
                "playbook_id": store_id,
                "playbook_name": name,
                "reason": reason,
                "current": current,
                "total": total,
            },
        )
    return {"id": store_id, "name": name}


def parallel_fetch_playbook_bodies(
    profile: CredentialProfile | str,
    rows: list[dict[str, str]],
    *,
    on_progress: Optional[ProgressCallback] = None,
) -> list[dict[str, str]]:
    """Download and cache playbook YAML for each planned row (parallel)."""
    if not rows:
        return []
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        pb_id = str(row.get("id") or "").strip()
        if not pb_id or pb_id in seen:
            continue
        seen.add(pb_id)
        deduped.append(row)

    workers = _parallel_workers(len(deduped))
    progress_lock = threading.Lock()
    counters = {"current": 0, "total": len(deduped)}
    fetched: list[dict[str, str]] = []
    errors: list[str] = []

    def _one(row: dict[str, str]) -> None:
        try:
            item = _fetch_playbook_row(
                resolved,
                row,
                on_progress=on_progress,
                progress_lock=progress_lock,
                counters=counters,
            )
            with progress_lock:
                fetched.append(item)
        except Exception as exc:
            with progress_lock:
                errors.append(f"{row.get('name') or row.get('id')}: {exc}")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, row) for row in deduped]
        for future in as_completed(futures):
            future.result()

    if errors:
        raise RuntimeError("Playbook body download failed: " + "; ".join(errors[:5]))
    return fetched


def ensure_analysis_playbook_bodies(
    profile: CredentialProfile | str,
    playbook_id: str,
    *,
    on_progress: Optional[ProgressCallback] = None,
) -> dict[str, Any]:
    """Re-plan and parallel-fetch playbook bodies until the tree is covered or nothing fetchable remains."""
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    all_fetched: list[dict[str, str]] = []
    last_plan: dict[str, Any] = {}

    for _round in range(_MAX_PLAN_ROUNDS):
        last_plan = plan_analysis_fetch_needs(resolved, playbook_id)
        rows = [
            row
            for row in (last_plan.get("playbook_bodies_needed") or [])
            if str(row.get("reason") or "") in _PLAYBOOK_FETCH_REASONS
        ]
        if not rows:
            break
        batch = parallel_fetch_playbook_bodies(resolved, rows, on_progress=on_progress)
        all_fetched.extend(batch)
    else:
        raise RuntimeError(
            f"Playbook body prefetch exceeded {_MAX_PLAN_ROUNDS} rounds; "
            "sub-playbook references may still be unresolved."
        )

    return {
        "playbooks_fetched": all_fetched,
        "playbooks_fetched_count": len(all_fetched),
        "final_fetch_plan": last_plan,
    }


def _collect_script_ids_for_playbook_ids(
    profile: CredentialProfile,
    playbook_ids: list[str],
) -> list[tuple[str, str]]:
    """Return (script_id, display_name) pairs referenced by cached playbook bodies."""
    resolver = CachePlaybookResolver(profile, allow_live_fetch=False, body_stale_policy="analysis")
    script_by_id, script_by_name = script_index_maps(profile)
    seen: set[str] = set()
    out: list[tuple[str, str]] = []

    for pb_id in playbook_ids:
        try:
            playbook = resolver.load(pb_id)
        except Exception:
            continue
        for node in (playbook.get("tasks") or {}).values():
            automation = resolve_automation_script(
                node,
                script_by_id=script_by_id,
                script_by_name=script_by_name,
            )
            if not automation or not automation.script_id:
                continue
            sid = str(automation.script_id)
            if sid in seen:
                continue
            seen.add(sid)
            out.append((sid, automation.canonical_name))

    return out


def _playbook_ids_in_tree(profile: CredentialProfile, root_ref: str) -> list[str]:
    resolver = CachePlaybookResolver(profile, allow_live_fetch=False, body_stale_policy="analysis")
    root = resolver.load(root_ref)
    queue = [str(root.get("id") or root_ref)]
    visited: set[str] = set()
    ids: list[str] = []

    while queue:
        pb_id = queue.pop(0)
        if pb_id in visited:
            continue
        visited.add(pb_id)
        ids.append(pb_id)
        try:
            body = resolver.load(pb_id)
        except Exception:
            continue
        for _task_id, pid, pname, _label in iter_sub_playbook_refs(body):
            target = resolver.resolve(pid, pname)
            if target and target not in visited:
                queue.append(str(target))
    return ids


def parallel_fetch_script_bodies(
    profile: CredentialProfile | str,
    script_rows: list[tuple[str, str]],
    *,
    on_progress: Optional[ProgressCallback] = None,
) -> list[dict[str, str]]:
    """Download automation script bodies missing from scripts/bodies/."""
    if not script_rows:
        return []
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    to_fetch: list[tuple[str, str]] = []
    for script_id, name in script_rows:
        if load_script_body(resolved, script_id) is not None:
            continue
        if find_script_in_index(resolved, script_id=script_id) is None:
            continue
        to_fetch.append((script_id, name))
    if not to_fetch:
        return []

    workers = _parallel_workers(len(to_fetch))
    progress_lock = threading.Lock()
    counters = {"current": 0, "total": len(to_fetch)}
    fetched: list[dict[str, str]] = []
    errors: list[str] = []

    def _one(script_id: str, name: str) -> None:
        try:
            with progress_lock:
                counters["current"] += 1
                current = counters["current"]
                total = counters["total"]
            if on_progress:
                on_progress(
                    {
                        "phase": "fetch_script",
                        "status": "running",
                        "script_id": script_id,
                        "script_name": name,
                        "current": current,
                        "total": total,
                    },
                )
            document = scripts_api.get_script(resolved, script_id)
            path = save_script_body(resolved, script_id, document)
            log_data_write("script body", detail=f"{name} ({script_id}) → {path}")
            if on_progress:
                on_progress(
                    {
                        "phase": "fetch_script",
                        "status": "complete",
                        "script_id": script_id,
                        "script_name": name,
                        "current": current,
                        "total": total,
                    },
                )
            with progress_lock:
                fetched.append({"id": script_id, "name": name})
        except Exception as exc:
            with progress_lock:
                errors.append(f"{name} ({script_id}): {exc}")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, sid, name) for sid, name in to_fetch]
        for future in as_completed(futures):
            future.result()

    if errors:
        op_info("Script body prefetch had %d error(s) (analysis continues): %s", len(errors), errors[:3])
    return fetched


def ensure_analysis_downloads(
    profile: CredentialProfile | str,
    playbook_id: str,
    *,
    on_progress: Optional[ProgressCallback] = None,
) -> dict[str, Any]:
    """Parallel-fetch missing playbook and script bodies for analysis."""
    playbook_result = ensure_analysis_playbook_bodies(profile, playbook_id, on_progress=on_progress)
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    try:
        pb_ids = _playbook_ids_in_tree(resolved, playbook_id)
    except Exception:
        pb_ids = [str(playbook_id)]
    script_rows = _collect_script_ids_for_playbook_ids(resolved, pb_ids)
    scripts_fetched = parallel_fetch_script_bodies(resolved, script_rows, on_progress=on_progress)
    return {
        **playbook_result,
        "scripts_fetched": scripts_fetched,
        "scripts_fetched_count": len(scripts_fetched),
    }
