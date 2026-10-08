"""Lab QA: bundle copy preview across copy modes (preview only, no execute)."""

from __future__ import annotations

import pytest

from cortex_ps_toolkit.bundles.copy import plan_bundle_copy
from cortex_ps_toolkit.scripts.service import list_cached_scripts

pytestmark = pytest.mark.integration

SOURCE = "xsoar-japac-dev"
TARGET = "personal-xsoar6"

MODES = [
    {"copy_mode": "skip", "overwrite": False, "stop_on_conflict": False},
    {"copy_mode": "overwrite", "overwrite": True, "stop_on_conflict": False},
    {"copy_mode": "skip", "overwrite": False, "stop_on_conflict": True},
    {"copy_mode": "copy_as_new", "overwrite": False, "stop_on_conflict": False, "rename_suffix": "_labqa"},
]


def _first_script_name(source: str) -> str | None:
    for row in list_cached_scripts(source):
        name = str(row.get("name") or row.get("id") or "").strip()
        if name:
            return name
    return None


@pytest.mark.parametrize("mode_kwargs", MODES, ids=[m.get("copy_mode", "?") for m in MODES])
def test_bundle_copy_preview_modes(
    available_lab_slugs: set[str],
    mode_kwargs: dict,
) -> None:
    if SOURCE not in available_lab_slugs or TARGET not in available_lab_slugs:
        pytest.skip(f"Lab pair {SOURCE} → {TARGET} not configured")

    script_name = _first_script_name(SOURCE)
    if not script_name:
        pytest.skip("No cached scripts on source — refresh scripts cache first")

    items = [{"asset": "scripts", "id": script_name, "name": script_name}]
    plan = plan_bundle_copy(SOURCE, TARGET, items, shallow_playbooks=True, **mode_kwargs)
    assert plan.get("plan_version") == 1
    assert plan.get("operation") == "bundles.copy"
    assert "sub_plans" in plan or plan.get("items") is not None
