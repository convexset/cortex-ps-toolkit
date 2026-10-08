"""Lab QA: bundle copy preview across copy modes (preview only, no execute)."""

from __future__ import annotations

import pytest

from cortex_ps_toolkit.bundles.copy import plan_bundle_copy

pytestmark = pytest.mark.integration

MODES = [
    {"copy_mode": "skip", "overwrite": False, "stop_on_conflict": False},
    {"copy_mode": "overwrite", "overwrite": True, "stop_on_conflict": False},
    {"copy_mode": "skip", "overwrite": False, "stop_on_conflict": True},
    {"copy_mode": "copy_as_new", "overwrite": False, "stop_on_conflict": False, "rename_suffix": "_labqa"},
]


@pytest.mark.parametrize("mode_kwargs", MODES, ids=[m.get("copy_mode", "?") for m in MODES])
def test_bundle_copy_preview_modes(
    available_lab_slugs: set[str],
    mode_kwargs: dict,
) -> None:
    source = "xsoar-japac-dev"
    target = "personal-xsoar6"
    if source not in available_lab_slugs or target not in available_lab_slugs:
        pytest.skip("Lab pair xsoar-japac-dev → personal-xsoar6 not configured")

    items = [
        {"asset": "scripts", "id": "NonExistentScriptForPreview", "name": "NonExistentScriptForPreview"},
    ]
    plan = plan_bundle_copy(source, target, items, shallow_playbooks=True, **mode_kwargs)
    assert plan.get("plan_version") == 1
    assert plan.get("operation") == "bundles.copy"
    assert "sub_plans" in plan or plan.get("items") is not None
