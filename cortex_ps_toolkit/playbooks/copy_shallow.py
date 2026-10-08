"""Shallow playbook copy: upload documents only; bind refs to target tenant cache."""

from __future__ import annotations

import copy
from typing import Any, Callable, Mapping, Optional, Sequence

from ..cache.ensure import ensure_playbooks_cache, ensure_scripts_cache
from ..content.copy_plan_params import normalize_copy_kwargs
from ..content.operation_plan import wrap_copy_plan
from ..content.post_copy_diff import (
    aggregate_copy_diff_report,
    apply_post_copy_diffs,
    new_copy_run_telemetry,
)
from ..core.batch_copy_progress import emit_copy_item_step, make_batch_copy_progress
from ..core.client import TenantApiError
from ..credentials import get_profile
from ..ops_log import op_action, op_info
from ..platforms import assert_operation_supported
from . import api
from .copy import plan_playbooks_copy
from .service import refresh_playbooks_cache
from .upload import save_playbook_document
from .yaml_bindings import prepare_playbook_bindings_for_upload
from ..scripts.copy import copy_scripts_to_tenant
from .copy import copy_playbooks_to_tenant


def _binding_rows_for_playbook(
    source_profile: str,
    target_profile: str,
    playbook_id: str,
) -> list[dict[str, Any]]:
    source = get_profile(source_profile)
    target = get_profile(target_profile)
    doc = api.get_playbook(source, playbook_id)
    probe = copy.deepcopy(doc)
    unresolved = prepare_playbook_bindings_for_upload(
        probe,
        target,
        source_profile=source,
    )
    rows: list[dict[str, Any]] = []
    for item in unresolved:
        rows.append(
            {
                "playbook_id": playbook_id,
                "playbook_name": str(doc.get("name") or playbook_id),
                "task_id": item.get("task_id"),
                "kind": item.get("kind") or "binding",
                "error": item.get("error") or "unresolved",
            },
        )
    return rows


def plan_shallow_playbooks_copy(
    source_profile: str,
    target_profile: str,
    playbook_ids: Sequence[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    copy_mode: Optional[str] = None,
    rename_suffix: str = "",
    rename_map: Optional[Mapping[str, str]] = None,
    wave_script_ids: Optional[Sequence[str]] = None,
    wave_playbook_ids: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    opts = normalize_copy_kwargs(
        overwrite=overwrite,
        stop_on_conflict=stop_on_conflict,
        copy_mode=copy_mode,
        rename_suffix=rename_suffix,
        rename_map=rename_map,
    )
    ensure_scripts_cache(get_profile(target_profile))
    ensure_playbooks_cache(get_profile(target_profile))

    base = plan_playbooks_copy(
        source_profile,
        target_profile,
        playbook_ids,
        overwrite=opts["overwrite"],
        stop_on_conflict=opts["stop_on_conflict"],
        copy_mode=opts["copy_mode"],
        rename_suffix=opts["rename_suffix"],
        rename_map=opts["rename_map"],
    )
    binding_table: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for playbook_id in playbook_ids:
        binding_table.extend(_binding_rows_for_playbook(source_profile, target_profile, playbook_id))

    if binding_table:
        warnings.append(
            {
                "code": "MISSING_BINDING",
                "message": (
                    f"{len(binding_table)} task binding(s) cannot be resolved on target yet; "
                    "upload may succeed but tasks can fail at runtime until dependencies exist."
                ),
            },
        )

    extra_steps: list[dict[str, Any]] = []
    wave_scripts = list(wave_script_ids or [])
    wave_playbooks = list(wave_playbook_ids or [])
    if wave_scripts:
        extra_steps.append(
            {
                "label": f"Wave 1: copy {len(wave_scripts)} script(s) required for bindings",
                "automated": True,
            },
        )
    if wave_playbooks:
        extra_steps.append(
            {
                "label": f"Wave {2 if wave_scripts else 1}: copy {len(wave_playbooks)} sub-playbook(s)",
                "automated": True,
            },
        )

    base["operation"] = "playbooks.copy_shallow"
    return wrap_copy_plan(
        base,
        operation="playbooks.copy_shallow",
        mode=opts["copy_mode"],
        rename_suffix=opts["rename_suffix"],
        extra_steps=extra_steps or None,
        extra_warnings=warnings,
        binding_table=binding_table,
    )


def copy_shallow_playbooks_to_tenant(
    source_profile: str,
    target_profile: str,
    playbook_ids: Sequence[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    copy_mode: Optional[str] = None,
    rename_suffix: str = "",
    rename_map: Optional[Mapping[str, str]] = None,
    wave_script_ids: Optional[Sequence[str]] = None,
    wave_playbook_ids: Optional[Sequence[str]] = None,
    post_copy_diff: bool = False,
    on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    source = get_profile(source_profile)
    target = get_profile(target_profile)
    assert_operation_supported("playbooks.copy", source.tenant_type)
    assert_operation_supported("playbooks.copy", target.tenant_type)

    progress = make_batch_copy_progress(
        title="Shallow Playbooks Copy",
        operation="playbooks.copy_shallow",
        on_progress=on_progress,
    )
    wave_results: dict[str, Any] = {}
    with op_action(
        "Shallow playbooks copy %s → %s (%d playbook(s))",
        source.slug,
        target.slug,
        len(playbook_ids),
    ):
        plan = plan_shallow_playbooks_copy(
            source_profile,
            target_profile,
            playbook_ids,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
            copy_mode=copy_mode,
            rename_suffix=rename_suffix,
            rename_map=rename_map,
            wave_script_ids=wave_script_ids,
            wave_playbook_ids=wave_playbook_ids,
        )
        progress.complete_stage()
        if plan["would_abort"]:
            return {
                "source_profile": source.slug,
                "target_profile": target.slug,
                "aborted": True,
                "reason": plan.get("abort_reason") or "Plan aborted",
                "conflicts": plan.get("conflicts") or [],
                "results": [],
            }

        if wave_script_ids:
            wave_results["scripts"] = copy_scripts_to_tenant(
                source_profile,
                target_profile,
                list(wave_script_ids),
                overwrite=False,
                stop_on_conflict=False,
            )
            refresh_playbooks_cache(target)
        if wave_playbook_ids:
            wave_results["playbooks"] = copy_playbooks_to_tenant(
                source_profile,
                target_profile,
                list(wave_playbook_ids),
                overwrite=False,
                stop_on_conflict=False,
            )

        shallow_out = copy_playbooks_to_tenant(
            source_profile,
            target_profile,
            playbook_ids,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
            copy_mode=copy_mode,
            rename_suffix=rename_suffix,
            rename_map=rename_map,
            post_copy_diff=post_copy_diff,
            on_progress=on_progress,
        )
        shallow_out["operation"] = "playbooks.copy_shallow"
        shallow_out["wave_results"] = wave_results
        shallow_out["binding_table"] = plan.get("binding_table") or []
        if post_copy_diff and shallow_out.get("copy_diff_report"):
            shallow_out["copy_diff_report"] = aggregate_copy_diff_report(shallow_out)
        shallow_out["telemetry"] = new_copy_run_telemetry(
            operation="playbooks.copy_shallow",
            post_copy_diff=post_copy_diff,
        )
        return shallow_out
