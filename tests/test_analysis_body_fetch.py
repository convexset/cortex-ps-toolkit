"""Tests for parallel analysis body prefetch."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.playbooks.analysis_body_fetch import (
    ensure_analysis_playbook_bodies,
    parallel_fetch_playbook_bodies,
)


@patch("cortex_ps_toolkit.playbooks.analysis_body_fetch.save_playbook_body")
@patch("cortex_ps_toolkit.playbooks.analysis_body_fetch.playbooks_api.get_playbook")
@patch("cortex_ps_toolkit.playbooks.analysis_body_fetch.get_profile")
def test_parallel_fetch_playbook_bodies_deduplicates(
    mock_get_profile,
    mock_get_playbook,
    mock_save,
) -> None:
    profile = MagicMock(slug="lab")
    mock_get_profile.return_value = profile
    mock_get_playbook.return_value = {"id": "pb-1", "name": "Sub", "tasks": {}}
    mock_save.return_value = "/tmp/pb-1.json"

    rows = [
        {"id": "pb-1", "name": "Sub", "reason": "missing_file"},
        {"id": "pb-1", "name": "Sub", "reason": "missing_file"},
    ]
    fetched = parallel_fetch_playbook_bodies("lab", rows)
    assert len(fetched) == 1
    mock_get_playbook.assert_called_once_with(profile, "pb-1")


@patch("cortex_ps_toolkit.playbooks.analysis_body_fetch.parallel_fetch_playbook_bodies")
@patch("cortex_ps_toolkit.playbooks.analysis_body_fetch.plan_analysis_fetch_needs")
@patch("cortex_ps_toolkit.playbooks.analysis_body_fetch.get_profile")
def test_ensure_analysis_playbook_bodies_replans_after_fetch(
    mock_get_profile,
    mock_plan,
    mock_parallel,
) -> None:
    mock_get_profile.return_value = MagicMock(slug="lab")
    mock_plan.side_effect = [
        {
            "playbook_bodies_needed": [{"id": "sub-1", "name": "Sub", "reason": "missing_file"}],
        },
        {"playbook_bodies_needed": []},
    ]
    mock_parallel.return_value = [{"id": "sub-1", "name": "Sub"}]

    result = ensure_analysis_playbook_bodies("lab", "root-id")
    assert result["playbooks_fetched_count"] == 1
    assert mock_plan.call_count == 2
    mock_parallel.assert_called_once()
