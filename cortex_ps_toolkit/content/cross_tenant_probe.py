"""Cross-tenant deep copy trials with post-copy fidelity comparison."""

from __future__ import annotations

from typing import Any, Literal, Optional

# Lab tenants used for copy/fidelity trials (excludes customer UAT tenants).
LAB_TRIAL_PROFILES: tuple[str, ...] = (
    "xsoar-japac-dev",
    "personal-xsoar6",
    "psojapac-xsiam",
    "cortex-cs-xdr5",
    "cortex-cs-agentix",
)


def lab_trial_targets(source_slug: str) -> list[str]:
    """Return lab tenant slugs excluding the source profile."""
    return [slug for slug in LAB_TRIAL_PROFILES if slug != source_slug]

from ..cache.ensure import ensure_analysis_caches
from ..credentials import CredentialProfile, get_profile
from ..playbooks import api as playbooks_api
from ..playbooks.analysis import analyze_playbook
from ..playbooks.cache import find_playbook_in_index
from ..playbooks.copy_components import copy_playbook_components_to_tenant, plan_playbook_components_copy
from ..playbooks.service import refresh_playbooks_cache
from ..scripts import api as scripts_api
from ..scripts.cache import find_script_in_index
from ..scripts.service import refresh_scripts_cache
from .representation import diff_representations

ComponentKind = Literal["playbook", "script"]


def _load_playbook_by_name(profile: CredentialProfile, name: str) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    entry = find_playbook_in_index(profile, name=name)
    if not entry or not entry.get("id"):
        return None, None
    playbook_id = str(entry["id"])
    return playbook_id, playbooks_api.get_playbook(profile, playbook_id)


def _load_script_by_name(profile: CredentialProfile, name: str) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    entry = find_script_in_index(profile, name=name)
    if not entry:
        return None, None
    script_id = str(entry.get("id") or entry.get("name") or "")
    if not script_id:
        return None, None
    try:
        doc = scripts_api.get_script(profile, script_id)
    except Exception:
        doc = scripts_api.get_script_by_name(profile, name)
    resolved_id = str(doc.get("id") or script_id)
    return resolved_id, doc


def compare_component(
    source: CredentialProfile,
    target: CredentialProfile,
    *,
    kind: ComponentKind,
    name: str,
    source_id: Optional[str] = None,
) -> dict[str, Any]:
    """Deep-compare one playbook or script between source and target tenants by name."""
    if kind == "playbook":
        src_id = source_id
        src_doc = playbooks_api.get_playbook(source, src_id) if src_id else None
        if src_doc is None:
            _, src_doc = _load_playbook_by_name(source, name)
        tgt_id, tgt_doc = _load_playbook_by_name(target, name)
    else:
        src_id = source_id
        if src_id:
            try:
                src_doc = scripts_api.get_script(source, src_id)
            except Exception:
                _, src_doc = _load_script_by_name(source, name)
        else:
            _, src_doc = _load_script_by_name(source, name)
        tgt_id, tgt_doc = _load_script_by_name(target, name)

    row: dict[str, Any] = {
        "kind": kind,
        "name": name,
        "source_id": src_id,
        "target_id": tgt_id,
        "found_on_target": tgt_doc is not None,
        "found_on_source": src_doc is not None,
    }
    if not src_doc:
        row["equal"] = False
        row["error"] = "missing on source"
        return row
    if not tgt_doc:
        row["equal"] = False
        row["error"] = "missing on target"
        return row

    diff = diff_representations(src_doc, tgt_doc, kind)
    row["equal"] = diff.equal
    row["differences"] = diff.differences[:50]
    row["difference_count"] = len(diff.differences)
    if len(diff.differences) > 50:
        row["differences_truncated"] = True
    return row


def compare_deep_copy_fidelity(
    source_slug: str,
    target_slug: str,
    root_playbook_id: str,
    *,
    analysis: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Compare all playbooks and scripts in a component-copy scope between tenants."""
    source = get_profile(source_slug)
    target = get_profile(target_slug)
    ensure_analysis_caches(source, force=True)
    refresh_playbooks_cache(target)
    refresh_scripts_cache(target)

    analysis = analysis or analyze_playbook(source_slug, root_playbook_id)
    components: list[dict[str, Any]] = []

    for entry in analysis.get("playbooks_in_tree") or []:
        pb_id = str(entry.get("id") or "")
        pb_name = str(entry.get("name") or "")
        if not pb_name:
            continue
        components.append(
            compare_component(
                source,
                target,
                kind="playbook",
                name=pb_name,
                source_id=pb_id or None,
            )
        )

    for script_row in analysis.get("scripts_used") or []:
        script_name = str(script_row.get("name") or "")
        if not script_name:
            continue
        components.append(
            compare_component(
                source,
                target,
                kind="script",
                name=script_name,
                source_id=str(script_row.get("script_id") or "") or None,
            )
        )

    equal_count = sum(1 for row in components if row.get("equal"))
    missing = [row for row in components if not row.get("found_on_target")]
    mismatched = [
        row for row in components
        if row.get("found_on_target") and not row.get("equal")
    ]

    return {
        "source_profile": source_slug,
        "target_profile": target_slug,
        "root_playbook_id": root_playbook_id,
        "root_playbook_name": analysis.get("root_playbook", {}).get("name"),
        "component_count": len(components),
        "equal_count": equal_count,
        "all_equal": equal_count == len(components) and not missing,
        "missing_on_target": missing,
        "mismatched": mismatched,
        "components": components,
    }


def run_deep_copy_trial(
    source_slug: str,
    target_slug: str,
    root_playbook_id: str,
    *,
    overwrite: bool = True,
    stop_on_conflict: bool = False,
) -> dict[str, Any]:
    """Deep-copy playbook components to target, then compare fidelity."""
    source = get_profile(source_slug)
    target = get_profile(target_slug)

    ensure_analysis_caches(source, force=True)
    plan = plan_playbook_components_copy(
        source_slug,
        target_slug,
        root_playbook_id,
        overwrite=overwrite,
        stop_on_conflict=stop_on_conflict,
    )
    analysis = analyze_playbook(source_slug, root_playbook_id)

    trial: dict[str, Any] = {
        "source_profile": source_slug,
        "source_platform": source.tenant_type.value,
        "target_profile": target_slug,
        "target_platform": target.tenant_type.value,
        "root_playbook_id": root_playbook_id,
        "root_playbook_name": plan.get("root_playbook_name"),
        "plan_would_abort": bool(plan.get("would_abort")),
        "missing_sub_playbooks": plan.get("missing_sub_playbooks") or [],
        "copy_scope": plan.get("analysis_summary") or {},
    }

    if plan.get("would_abort") or plan.get("missing_sub_playbooks"):
        trial["copy"] = {"aborted": True, "reason": "plan would abort or missing sub-playbooks"}
        trial["fidelity"] = None
        return trial

    copy_result = copy_playbook_components_to_tenant(
        source_slug,
        target_slug,
        root_playbook_id,
        overwrite=overwrite,
        stop_on_conflict=stop_on_conflict,
    )
    trial["copy"] = copy_result
    if copy_result.get("aborted"):
        trial["fidelity"] = None
        return trial

    trial["fidelity"] = compare_deep_copy_fidelity(
        source_slug,
        target_slug,
        root_playbook_id,
        analysis=analysis,
    )
    return trial


def run_trial_series(
    source_slug: str,
    root_playbook_id: str,
    target_slugs: list[str],
    *,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Run deep-copy trials from one source to many targets sequentially."""
    results: list[dict[str, Any]] = []
    for target_slug in target_slugs:
        if target_slug == source_slug:
            continue
        try:
            result = run_deep_copy_trial(
                source_slug,
                target_slug,
                root_playbook_id,
                overwrite=overwrite,
            )
        except Exception as exc:
            result = {
                "source_profile": source_slug,
                "target_profile": target_slug,
                "root_playbook_id": root_playbook_id,
                "error": str(exc),
                "copy": None,
                "fidelity": None,
            }
        results.append(result)
    passed = sum(
        1 for row in results
        if row.get("fidelity") and row["fidelity"].get("all_equal")
    )
    return {
        "source_profile": source_slug,
        "root_playbook_id": root_playbook_id,
        "targets": target_slugs,
        "trial_count": len(results),
        "fidelity_pass_count": passed,
        "results": results,
    }
