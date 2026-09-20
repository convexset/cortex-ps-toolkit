"""Cross-tenant copy for correlation rules."""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..credentials import CredentialProfile, get_profile
from ..design_content.copy_progress import notify_item_copied
from ..platforms import assert_operation_supported
from . import api
from .plan import plan_correlation_copy
from .service import refresh_section_cache
from .types import OPERATION_BY_SECTION


def copy_correlation_rules_to_tenant(
    source_profile: CredentialProfile | str,
    target_profile: CredentialProfile | str,
    rule_names: list[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    name_suffix: Optional[str] = None,
    on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    source = get_profile(source_profile) if isinstance(source_profile, str) else source_profile
    target = get_profile(target_profile) if isinstance(target_profile, str) else target_profile
    assert_operation_supported(OPERATION_BY_SECTION["correlation-rules"], source.tenant_type)
    assert_operation_supported(OPERATION_BY_SECTION["correlation-rules"], target.tenant_type)

    plan = plan_correlation_copy(
        source,
        target,
        rule_names,
        overwrite=overwrite,
        stop_on_conflict=stop_on_conflict,
        name_suffix=name_suffix,
    )
    entries = plan["entries"]
    if plan.get("has_conflicts"):
        return {**plan, "executed": False, "error": "conflicts detected (stop_on_conflict)"}

    results: list[dict[str, Any]] = []
    for entry in entries:
        action = entry.get("action")
        if action in ("skip", "missing"):
            results.append({**entry, "status": "skipped"})
            continue
        source_rule = api.get_correlation_rule(source, str(entry["source_name"]))
        if not source_rule:
            results.append({**entry, "status": "skipped", "error": "source missing"})
            continue
        if on_progress:
            on_progress({"phase": "step", "asset": "correlation-rules", "target_name": entry.get("target_name")})
        write_doc = api.prepare_correlation_write(source_rule, new_name=str(entry["target_name"]))
        _, status = api.insert_correlation_rules(target, [write_doc])
        result_entry = {**entry, "status": status}
        results.append(result_entry)
        notify_item_copied(on_progress, "correlation-rules", result_entry)

    refresh_section_cache(target, "correlation-rules")
    return {
        **plan,
        "results": results,
        "executed": True,
    }
