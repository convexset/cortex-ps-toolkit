"""Cross-tenant copy for correlation rules."""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..core.batch_copy_progress import emit_copy_item_step, make_batch_copy_progress
from ..credentials import CredentialProfile, get_profile
from ..ops_log import op_action, op_info
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

    progress = make_batch_copy_progress(
        title="Correlation Rules Copy Progress",
        operation="platform_admin.correlation_copy",
        on_progress=on_progress,
    )
    with op_action(
        "Correlation rules copy %s → %s (%d rule(s))",
        source.slug,
        target.slug,
        len(rule_names),
    ):
        plan = plan_correlation_copy(
            source,
            target,
            rule_names,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
            name_suffix=name_suffix,
        )
        progress.complete_stage()
        entries = plan["entries"]
        if plan.get("has_conflicts"):
            return {**plan, "executed": False, "error": "conflicts detected (stop_on_conflict)"}

        results: list[dict[str, Any]] = []
        total = len(entries)
        for index, entry in enumerate(entries, start=1):
            action = entry.get("action")
            if action in ("skip", "missing"):
                results.append({**entry, "status": "skipped"})
                continue
            source_rule = api.get_correlation_rule(source, str(entry["source_name"]))
            if not source_rule:
                results.append({**entry, "status": "skipped", "error": "source missing"})
                continue
            name = str(entry.get("target_name") or entry.get("source_name") or "")
            emit_copy_item_step(
                on_progress,
                source=source.slug,
                target=target.slug,
                item_label="correlation rule",
                name=name,
                index=index,
                total=total,
            )
            op_info(
                "Copying correlation rule %r (%d/%d) %s → %s",
                name,
                index,
                total,
                source.slug,
                target.slug,
            )
            write_doc = api.prepare_correlation_write(source_rule, new_name=str(entry["target_name"]))
            _, status = api.insert_correlation_rules(target, [write_doc])
            result_entry = {**entry, "status": status}
            results.append(result_entry)
            notify_item_copied(on_progress, "correlation-rules", result_entry)

        progress.complete_stage()
        op_info("Refreshing correlation rules cache on %s after copy", target.slug)
        refresh_section_cache(target, "correlation-rules")
        progress.complete_stage()
        return {
            **plan,
            "results": results,
            "executed": True,
        }
