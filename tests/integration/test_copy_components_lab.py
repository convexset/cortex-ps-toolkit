"""Lab: deep copy (copy-components) preview only — no tenant writes."""

from __future__ import annotations

import pytest

from cortex_ps_toolkit.playbooks.cache import load_playbooks_index
from cortex_ps_toolkit.playbooks.copy_components import plan_playbook_components_copy
from cortex_ps_toolkit.credentials import get_profile
from cortex_ps_toolkit.playbooks.service import refresh_playbooks_cache

pytestmark = pytest.mark.integration

SOURCE = "xsoar-japac-dev"
TARGET = "personal-xsoar6"


def _root_playbook_id(slug: str) -> str | None:
    refresh_playbooks_cache(slug)
    index = load_playbooks_index(get_profile(slug))
    for row in index.get("playbooks") or []:
        if isinstance(row, dict) and row.get("id"):
            return str(row["id"])
    return None


def test_copy_components_preview_lab_pair(available_lab_slugs: set[str]) -> None:
    if SOURCE not in available_lab_slugs or TARGET not in available_lab_slugs:
        pytest.skip(f"Lab pair {SOURCE} → {TARGET} not configured")

    playbook_id = _root_playbook_id(SOURCE)
    if not playbook_id:
        pytest.skip("No playbooks in source cache — refresh playbooks first")

    plan = plan_playbook_components_copy(
        SOURCE,
        TARGET,
        playbook_id,
        cache_only=True,
        skip_cache_refresh=True,
    )
    assert plan.get("plan_version") == 1
    assert plan.get("operation") == "playbooks.copy_components"
    assert plan.get("root_playbook") or plan.get("analysis_summary")
