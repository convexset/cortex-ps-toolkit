"""Cross-tenant copy for indicators (IOCs)."""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..credentials import CredentialProfile, get_profile
from ..platforms import Platform, assert_operation_supported
from . import api
from .plan import plan_indicator_copy
from .service import refresh_section_cache
from .types import OPERATION_BY_SECTION


def copy_indicators_to_tenant(
    source_profile: CredentialProfile | str,
    target_profile: CredentialProfile | str,
    indicator_ids: list[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    source = get_profile(source_profile) if isinstance(source_profile, str) else source_profile
    target = get_profile(target_profile) if isinstance(target_profile, str) else target_profile
    assert_operation_supported(OPERATION_BY_SECTION["indicators"], source.tenant_type)
    assert_operation_supported(OPERATION_BY_SECTION["indicators"], target.tenant_type)

    plan = plan_indicator_copy(
        source,
        target,
        indicator_ids,
        overwrite=overwrite,
        stop_on_conflict=stop_on_conflict,
    )
    if plan.get("has_conflicts"):
        return {**plan, "executed": False, "error": "conflicts detected (stop_on_conflict)"}

    results: list[dict[str, Any]] = []
    target_is_xsoar = target.tenant_type in (Platform.XSOAR6, Platform.XSOAR8)

    for entry in plan["entries"]:
        action = entry.get("action")
        if action in ("skip", "missing", "incompatible"):
            results.append({**entry, "status": "skipped"})
            continue
        source_doc = api.get_indicator(source, str(entry["source_id"]))
        if not source_doc:
            results.append({**entry, "status": "skipped", "error": "source missing"})
            continue
        if on_progress:
            on_progress({"phase": "step", "section": "indicators", "source_id": entry.get("source_id")})
        if target_is_xsoar:
            _, status = api.create_xsoar_indicator(target, source_doc)
        else:
            write_doc = api.prepare_cortex_indicator_write(source_doc)
            _, status = api.insert_indicators(target, [write_doc])
        results.append({**entry, "status": status})

    refresh_section_cache(target, "indicators")
    return {
        **plan,
        "results": results,
        "executed": True,
    }
