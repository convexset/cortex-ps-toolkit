"""Cross-tenant copy for indicators (IOCs)."""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..core.batch_copy_progress import emit_copy_item_step, make_batch_copy_progress
from ..credentials import CredentialProfile, get_profile
from ..ops_log import op_action, op_info
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

    progress = make_batch_copy_progress(
        title="Indicator Copy Progress",
        operation="platform_admin.indicator_copy",
        on_progress=on_progress,
    )
    with op_action(
        "Indicator copy %s → %s (%d indicator(s))",
        source.slug,
        target.slug,
        len(indicator_ids),
    ):
        plan = plan_indicator_copy(
            source,
            target,
            indicator_ids,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
        )
        progress.complete_stage()
        if plan.get("has_conflicts"):
            return {**plan, "executed": False, "error": "conflicts detected (stop_on_conflict)"}

        results: list[dict[str, Any]] = []
        target_is_xsoar = target.tenant_type in (Platform.XSOAR6, Platform.XSOAR8)
        entries = plan["entries"]
        total = len(entries)

        for index, entry in enumerate(entries, start=1):
            action = entry.get("action")
            if action in ("skip", "missing", "incompatible"):
                results.append({**entry, "status": "skipped"})
                continue
            source_doc = api.get_indicator(source, str(entry["source_id"]))
            if not source_doc:
                results.append({**entry, "status": "skipped", "error": "source missing"})
                continue
            label = str(entry.get("source_id") or entry.get("target_name") or index)
            emit_copy_item_step(
                on_progress,
                source=source.slug,
                target=target.slug,
                item_label="indicator",
                name=label,
                index=index,
                total=total,
                item_id=str(entry.get("source_id") or ""),
            )
            op_info(
                "Copying indicator %s (%d/%d) %s → %s",
                label,
                index,
                total,
                source.slug,
                target.slug,
            )
            if target_is_xsoar:
                _, status = api.create_xsoar_indicator(target, source_doc)
            else:
                write_doc = api.prepare_cortex_indicator_write(source_doc)
                _, status = api.insert_indicators(target, [write_doc])
            results.append({**entry, "status": status})

        progress.complete_stage()
        op_info("Refreshing indicators cache on %s after copy", target.slug)
        refresh_section_cache(target, "indicators")
        progress.complete_stage()
        return {
            **plan,
            "results": results,
            "executed": True,
        }
