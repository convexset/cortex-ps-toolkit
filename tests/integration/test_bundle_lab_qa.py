"""Extended bundle lab QA: preview matrix + optional execute (env-gated)."""

from __future__ import annotations

import os
import uuid

import pytest

from cortex_ps_toolkit.bundles.copy import copy_bundle_to_tenant, plan_bundle_copy
from cortex_ps_toolkit.scripts.service import list_cached_scripts

pytestmark = pytest.mark.integration

SOURCE = "xsoar-japac-dev"
TARGET = "personal-xsoar6"

MODES = [
    {"copy_mode": "skip", "overwrite": False, "stop_on_conflict": False, "post_copy_diff": False},
    {"copy_mode": "overwrite", "overwrite": True, "stop_on_conflict": False, "post_copy_diff": True},
    {"copy_mode": "skip", "overwrite": False, "stop_on_conflict": True, "post_copy_diff": False},
    {
        "copy_mode": "copy_as_new",
        "overwrite": False,
        "stop_on_conflict": False,
        "rename_suffix": "_labqa",
        "post_copy_diff": True,
    },
]


def _lab_pair_configured(available: set[str]) -> bool:
    return SOURCE in available and TARGET in available


def _first_copyable_script_slug(source: str) -> str | None:
    rows = list_cached_scripts(source)
    for row in rows:
        name = str(row.get("name") or row.get("id") or "").strip()
        if name and row.get("copyable", True) is not False:
            return name
    return None


@pytest.mark.parametrize("mode_kwargs", MODES, ids=[str(m.get("copy_mode")) for m in MODES])
def test_bundle_copy_preview_lab_matrix(available_lab_slugs: set[str], mode_kwargs: dict) -> None:
    if not _lab_pair_configured(available_lab_slugs):
        pytest.skip(f"Lab pair {SOURCE} → {TARGET} not configured")

    script_name = _first_copyable_script_slug(SOURCE)
    if not script_name:
        pytest.skip("No cached scripts on source — refresh scripts cache first")

    items = [{"asset": "scripts", "id": script_name, "name": script_name}]
    plan = plan_bundle_copy(
        SOURCE,
        TARGET,
        items,
        shallow_playbooks=True,
        **{k: v for k, v in mode_kwargs.items() if k != "post_copy_diff"},
    )
    assert plan.get("plan_version") == 1
    assert plan.get("operation") == "bundles.copy"
    assert isinstance(plan.get("sub_plans"), list)


def test_bundle_mixed_basket_preview_when_cache_populated(available_lab_slugs: set[str]) -> None:
    if not _lab_pair_configured(available_lab_slugs):
        pytest.skip(f"Lab pair {SOURCE} → {TARGET} not configured")

    script_name = _first_copyable_script_slug(SOURCE)
    if not script_name:
        pytest.skip("No scripts on source cache")

    from cortex_ps_toolkit.design_content.service import list_cached_items

    design_row = None
    for row in list_cached_items(SOURCE, "incident-fields"):
        item_id = str(row.get("id") or row.get("name") or "").strip()
        if item_id:
            design_row = {"asset": "incident-fields", "id": item_id, "name": str(row.get("name") or item_id)}
            break

    items = [{"asset": "scripts", "id": script_name, "name": script_name}]
    if design_row:
        items.append(design_row)

    plan = plan_bundle_copy(
        SOURCE,
        TARGET,
        items,
        shallow_playbooks=True,
        copy_mode="copy_as_new",
        rename_suffix="_mixed",
    )
    assert plan["plan_version"] == 1
    phases = {sub.get("phase") for sub in (plan.get("sub_plans") or [])}
    assert "scripts" in phases
    if design_row:
        assert len(plan.get("design_items") or []) >= 1
        assert any(w.get("code") == "DESIGN_PHASE" for w in (plan.get("warnings") or []))


@pytest.mark.integration
def test_bundle_execute_copy_as_new_script_env_gated(available_lab_slugs: set[str]) -> None:
    if os.environ.get("CORTEX_PS_BUNDLE_LAB_EXECUTE") != "1":
        pytest.skip("Set CORTEX_PS_BUNDLE_LAB_EXECUTE=1 to run live bundle execute QA")

    if not _lab_pair_configured(available_lab_slugs):
        pytest.skip(f"Lab pair {SOURCE} → {TARGET} not configured")

    script_name = _first_copyable_script_slug(SOURCE)
    if not script_name:
        pytest.skip("No scripts on source cache")

    suffix = f"_cptkqa_{uuid.uuid4().hex[:8]}"
    items = [{"asset": "scripts", "id": script_name, "name": script_name}]
    plan = plan_bundle_copy(
        SOURCE,
        TARGET,
        items,
        shallow_playbooks=True,
        copy_mode="copy_as_new",
        rename_suffix=suffix,
    )
    if plan.get("would_abort"):
        pytest.skip(f"Plan would abort: {plan.get('abort_reason')}")

    result = copy_bundle_to_tenant(
        SOURCE,
        TARGET,
        items,
        shallow_playbooks=True,
        copy_mode="copy_as_new",
        rename_suffix=suffix,
        post_copy_diff=True,
    )
    assert not result.get("aborted"), result.get("reason") or result
    script_phase = (result.get("results") or {}).get("scripts") or {}
    assert script_phase.get("results") or script_phase.get("copy_diff_report") is not None
