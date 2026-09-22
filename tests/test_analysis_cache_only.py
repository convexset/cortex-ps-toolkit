"""Tests for cache-only playbook analysis."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cortex_ps_toolkit.playbooks.analysis import analyze_playbook
from cortex_ps_toolkit.playbooks.resolver import CachePlaybookResolver


@patch("cortex_ps_toolkit.playbooks.analysis.ensure_analysis_downloads")
@patch("cortex_ps_toolkit.playbooks.analysis.check_analysis_caches")
@patch("cortex_ps_toolkit.playbooks.analysis.script_index_maps")
@patch("cortex_ps_toolkit.playbooks.analysis.find_script_in_index")
@patch.object(CachePlaybookResolver, "load")
@patch.object(CachePlaybookResolver, "resolve")
@patch.object(CachePlaybookResolver, "_build_index")
@patch("cortex_ps_toolkit.playbooks.analysis.get_profile")
def test_analyze_playbook_cache_only_skips_refresh(
    mock_get_profile,
    mock_build_index,
    mock_resolve,
    mock_load,
    mock_find_script,
    mock_script_maps,
    mock_check,
    mock_prefetch,
) -> None:
    mock_prefetch.return_value = {
        "playbooks_fetched": [],
        "playbooks_fetched_count": 0,
        "scripts_fetched": [],
        "scripts_fetched_count": 0,
    }
    mock_get_profile.return_value = MagicMock(slug="lab")
    mock_build_index.return_value = None
    mock_resolve.return_value = None
    mock_load.return_value = {
        "id": "root-id",
        "name": "Main PB",
        "tasks": {"0": {"type": "start", "task": {"name": "Start"}}},
    }
    mock_script_maps.return_value = ({}, {})
    mock_find_script.return_value = None
    mock_check.return_value = {"profile": "lab", "stale_scopes": ["playbooks"], "any_stale": True}

    result = analyze_playbook("lab", "root-id", cache_only=True, skip_cache_refresh=True)

    mock_check.assert_called_once()
    assert result["cache_only"] is True


@patch("cortex_ps_toolkit.playbooks.analysis.ensure_analysis_downloads")
@patch("cortex_ps_toolkit.playbooks.analysis.ensure_analysis_caches")
@patch("cortex_ps_toolkit.playbooks.analysis.script_index_maps")
@patch.object(CachePlaybookResolver, "load")
@patch.object(CachePlaybookResolver, "_build_index")
@patch("cortex_ps_toolkit.playbooks.analysis.get_profile")
def test_analyze_playbook_default_refreshes_elective_caches(
    mock_get_profile,
    mock_build_index,
    mock_load,
    mock_script_maps,
    mock_ensure,
    mock_prefetch,
) -> None:
    mock_prefetch.return_value = {
        "playbooks_fetched": [],
        "playbooks_fetched_count": 0,
        "scripts_fetched": [],
        "scripts_fetched_count": 0,
    }
    mock_get_profile.return_value = MagicMock(slug="lab")
    mock_build_index.return_value = None
    mock_load.return_value = {
        "id": "root-id",
        "name": "Main PB",
        "tasks": {"0": {"type": "start", "task": {"name": "Start"}}},
    }
    mock_script_maps.return_value = ({}, {})
    mock_ensure.return_value = {"profile": "lab"}

    analyze_playbook("lab", "root-id")

    mock_ensure.assert_called_once()
