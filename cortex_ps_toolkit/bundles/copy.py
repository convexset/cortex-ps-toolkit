"""Cross-tenant copy for extended solution bundles."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from ..content.copy_plan_params import integration_copy_plan_kwargs, normalize_copy_kwargs
from ..content.operation_plan import wrap_copy_plan
from ..credentials import get_profile
from ..design_content.bundle_presets import resolve_bundle_items
from ..design_content.orchestrator import execute_cross_tenant_workflow
from ..lists.copy import copy_lists_to_tenant, plan_lists_copy
from ..playbooks.copy import copy_playbooks_to_tenant, plan_playbooks_copy
from ..playbooks.copy_shallow import plan_shallow_playbooks_copy
from ..integrations.copy import copy_integrations_to_tenant, plan_integrations_copy
from ..content.post_copy_diff import finalize_bundle_copy_diff_metadata
from ..scripts.copy import copy_scripts_to_tenant, plan_scripts_copy


def _selections_from_design_items(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    selections: dict[str, list[str]] = {}
    correlation: list[str] = []
    for row in items:
        asset = str(row.get("asset") or "").strip()
        item_id = str(row.get("id") or "").strip()
        if not asset or not item_id:
            continue
        if asset == "correlation-rules":
            correlation.append(str(row.get("name") or item_id))
            continue
        selections.setdefault(asset, []).append(item_id)
    if correlation:
        selections["_correlation_rule_names"] = correlation
    return selections


def _partition_items(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "design": [],
        "lists": [],
        "scripts": [],
        "playbooks": [],
        "integrations": [],
    }
    for row in items:
        asset = str(row.get("asset") or row.get("kind") or "").strip()
        if asset in buckets:
            buckets[asset].append(row)
        elif asset in ("incident-types", "incident-fields", "layouts", "classifiers", "preprocess", "correlation-rules"):
            buckets["design"].append(row)
    return buckets


def plan_bundle_copy(
    source_profile: str,
    target_profile: str,
    items: Sequence[dict[str, Any]],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    copy_mode: Optional[str] = None,
    rename_suffix: str = "",
    rename_map: Optional[Mapping[str, str]] = None,
    shallow_playbooks: bool = True,
) -> dict[str, Any]:
    opts = normalize_copy_kwargs(
        overwrite=overwrite,
        stop_on_conflict=stop_on_conflict,
        copy_mode=copy_mode,
        rename_suffix=rename_suffix,
        rename_map=rename_map,
    )
    resolved = resolve_bundle_items(source_profile, list(items))
    if resolved.get("missing_count"):
        missing = resolved.get("missing") or []
        names = ", ".join(str(m.get("name") or m.get("id")) for m in missing[:6])
        raise ValueError(f"Bundle references missing on source: {names}")

    buckets = _partition_items(resolved["items"])
    list_ids = [str(i.get("id")) for i in buckets["lists"]]
    script_ids = [str(i.get("id")) for i in buckets["scripts"]]
    playbook_ids = [str(i.get("id")) for i in buckets["playbooks"]]
    integration_ids = [str(i.get("id")) for i in buckets["integrations"]]

    sub_plans: list[dict[str, Any]] = []
    flat_items: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    would_abort = False

    if integration_ids:
        ip = plan_integrations_copy(
            source_profile,
            target_profile,
            integration_ids,
            **integration_copy_plan_kwargs(opts),
        )
        sub_plans.append({"phase": "integrations", "plan": ip})
        flat_items.extend(ip.get("items") or [])
        would_abort = would_abort or bool(ip.get("would_abort"))
    if script_ids:
        sp = plan_scripts_copy(source_profile, target_profile, script_ids, **opts)
        sub_plans.append({"phase": "scripts", "plan": sp})
        flat_items.extend(sp.get("items") or [])
        would_abort = would_abort or bool(sp.get("would_abort"))
    if playbook_ids:
        if shallow_playbooks:
            pp = plan_shallow_playbooks_copy(source_profile, target_profile, playbook_ids, **opts)
        else:
            pp = plan_playbooks_copy(source_profile, target_profile, playbook_ids, **opts)
        sub_plans.append({"phase": "playbooks", "plan": pp})
        flat_items.extend(pp.get("items") or [])
        would_abort = would_abort or bool(pp.get("would_abort"))
        if pp.get("binding_table"):
            warnings.append({"code": "SHALLOW_BINDINGS", "message": "See playbook binding_table in sub-plan."})
    if list_ids:
        lp = plan_lists_copy(source_profile, target_profile, list_ids, **opts)
        sub_plans.append({"phase": "lists", "plan": lp})
        flat_items.extend(lp.get("items") or [])
        would_abort = would_abort or bool(lp.get("would_abort"))
    if buckets["design"]:
        warnings.append(
            {
                "code": "DESIGN_PHASE",
                "message": f"{len(buckets['design'])} design asset(s) import via bundle orchestrator after content copy.",
            },
        )

    legacy = {
        "source_profile": get_profile(source_profile).slug,
        "target_profile": get_profile(target_profile).slug,
        "items": flat_items,
        "sub_plans": sub_plans,
        "design_items": buckets["design"],
        "would_abort": would_abort,
        "counts": {
            "total": len(flat_items) + len(buckets["design"]),
            "copy": sum(p["plan"].get("counts", {}).get("copy", 0) for p in sub_plans),
            "update": sum(p["plan"].get("counts", {}).get("update", 0) for p in sub_plans),
            "skip": sum(p["plan"].get("counts", {}).get("skip", 0) for p in sub_plans),
            "conflict": sum(p["plan"].get("counts", {}).get("conflict", 0) for p in sub_plans),
        },
        "conflicts": [],
    }
    extra_steps = [
        {"label": "Phase 1: integration definitions (if any)", "automated": True},
        {"label": "Phase 2: scripts (if any)", "automated": True},
        {"label": "Phase 3: playbooks shallow waves (if any)", "automated": True},
        {"label": "Phase 4: lists (if any)", "automated": True},
        {"label": "Phase 5: design bundle import", "automated": True},
    ]
    return wrap_copy_plan(
        legacy,
        operation="bundles.copy",
        mode=opts["copy_mode"],
        rename_suffix=opts["rename_suffix"],
        extra_steps=extra_steps,
        extra_warnings=warnings,
    )


def copy_bundle_to_tenant(
    source_profile: str,
    target_profile: str,
    items: Sequence[dict[str, Any]],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    copy_mode: Optional[str] = None,
    rename_suffix: str = "",
    rename_map: Optional[Mapping[str, str]] = None,
    shallow_playbooks: bool = True,
    post_copy_diff: bool = False,
    on_progress: Optional[Any] = None,
) -> dict[str, Any]:
    plan = plan_bundle_copy(
        source_profile,
        target_profile,
        items,
        overwrite=overwrite,
        stop_on_conflict=stop_on_conflict,
        copy_mode=copy_mode,
        rename_suffix=rename_suffix,
        rename_map=rename_map,
        shallow_playbooks=shallow_playbooks,
    )
    if plan["would_abort"]:
        return {
            "aborted": True,
            "reason": plan.get("abort_reason") or "Bundle copy plan aborted",
            "plan": plan,
            "results": {},
        }

    opts = normalize_copy_kwargs(
        overwrite=overwrite,
        stop_on_conflict=stop_on_conflict,
        copy_mode=copy_mode,
        rename_suffix=rename_suffix,
        rename_map=rename_map,
    )
    resolved = resolve_bundle_items(source_profile, list(items))
    buckets = _partition_items(resolved["items"])
    results: dict[str, Any] = {}

    script_ids = [str(i.get("id")) for i in buckets["scripts"]]
    playbook_ids = [str(i.get("id")) for i in buckets["playbooks"]]
    list_ids = [str(i.get("id")) for i in buckets["lists"]]
    integration_ids = [str(i.get("id")) for i in buckets["integrations"]]

    if integration_ids:
        results["integrations"] = copy_integrations_to_tenant(
            source_profile,
            target_profile,
            integration_ids,
            **integration_copy_plan_kwargs(opts),
        )
    if script_ids:
        results["scripts"] = copy_scripts_to_tenant(
            source_profile,
            target_profile,
            script_ids,
            on_progress=on_progress,
            post_copy_diff=post_copy_diff,
            **opts,
        )
    if playbook_ids:
        if shallow_playbooks:
            from ..playbooks.copy_shallow import copy_shallow_playbooks_to_tenant

            results["playbooks"] = copy_shallow_playbooks_to_tenant(
                source_profile,
                target_profile,
                playbook_ids,
                on_progress=on_progress,
                post_copy_diff=post_copy_diff,
                **opts,
            )
        else:
            results["playbooks"] = copy_playbooks_to_tenant(
                source_profile,
                target_profile,
                playbook_ids,
                on_progress=on_progress,
                post_copy_diff=post_copy_diff,
                **opts,
            )
    if list_ids:
        results["lists"] = copy_lists_to_tenant(
            source_profile,
            target_profile,
            list_ids,
            on_progress=on_progress,
            post_copy_diff=post_copy_diff,
            **opts,
        )
    if buckets["design"]:
        raw_selections = _selections_from_design_items(buckets["design"])
        correlation_rule_names = list(raw_selections.pop("_correlation_rule_names", []) or [])
        results["design"] = execute_cross_tenant_workflow(
            source_profile,
            target_profile,
            raw_selections,
            overwrite=opts["overwrite"],
            stop_on_conflict=opts["stop_on_conflict"],
            include_correlation_rules=bool(correlation_rule_names),
            correlation_rule_names=correlation_rule_names or None,
        )

    out: dict[str, Any] = {
        "source_profile": plan["source_profile"],
        "target_profile": plan["target_profile"],
        "operation": "bundles.copy",
        "results": results,
    }
    if post_copy_diff:
        out["post_copy_diff"] = True
        finalize_bundle_copy_diff_metadata(out)
    return out
