"""Tests for playbook analysis fetch planning."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.playbooks.analysis_fetch_plan import plan_analysis_fetch_needs


@patch("cortex_ps_toolkit.playbooks.analysis_fetch_plan.lookup_playbook_body")
@patch("cortex_ps_toolkit.playbooks.analysis_fetch_plan.check_analysis_caches")
@patch("cortex_ps_toolkit.playbooks.analysis_fetch_plan.load_playbooks_index")
@patch("cortex_ps_toolkit.playbooks.analysis_fetch_plan.count_playbook_bodies_on_disk")
@patch("cortex_ps_toolkit.playbooks.analysis_fetch_plan.CachePlaybookResolver")
@patch("cortex_ps_toolkit.playbooks.analysis_fetch_plan.get_profile")
def test_plan_classifies_missing_file(
    mock_get_profile,
    mock_resolver_cls,
    mock_body_count,
    mock_load_index,
    mock_check,
    mock_lookup,
) -> None:
    mock_get_profile.return_value = MagicMock(slug="lab")
    mock_check.return_value = {"stale_scopes": [], "any_stale": False}
    mock_load_index.return_value = {"playbooks": [{"id": "root-id"}]}
    mock_body_count.return_value = 2
    resolver = MagicMock()
    resolver.resolve.side_effect = lambda pid, pname: pid or "root-id"
    mock_resolver_cls.return_value = resolver

    missing = MagicMock(
        status="missing_file",
        playbook=None,
        canonical_id="root-id",
        name="Root PB",
    )
    mock_lookup.return_value = missing

    plan = plan_analysis_fetch_needs("lab", "root-id")

    assert plan["index_playbook_count"] == 1
    assert plan["playbook_bodies_on_disk_count"] == 2
    assert plan["playbook_bodies_missing_file_count"] == 1
    assert plan["playbook_bodies_needed"][0]["reason"] == "missing_file"
