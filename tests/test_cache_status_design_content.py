"""Cache status includes design content and platform admin scopes."""

from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.cache.status import cache_status_for_profile
from cortex_ps_toolkit.design_content.types import ASSET_KINDS
from cortex_ps_toolkit.platform_admin.types import ADMIN_SECTIONS


@patch("cortex_ps_toolkit.cache.status.load_scripts_index", return_value={"scripts": []})
@patch("cortex_ps_toolkit.cache.status.load_playbooks_index", return_value={"playbooks": []})
@patch("cortex_ps_toolkit.cache.status.load_lists_index", return_value={"lists": []})
@patch("cortex_ps_toolkit.cache.status.load_design_index", return_value={"items": [], "refreshed_at": None})
@patch("cortex_ps_toolkit.cache.status.load_admin_index", return_value={"items": [], "refreshed_at": None})
@patch("cortex_ps_toolkit.cache.status.get_profile")
def test_cache_status_includes_design_and_admin_scopes(
    mock_get_profile,
    _admin,
    _design,
    _lists,
    _playbooks,
    _scripts,
) -> None:
    profile = type(
        "Profile",
        (),
        {"slug": "lab", "cache_key": "lab-key", "cache_ttl_seconds": None, "max_inflight_per_host": None, "max_inflight_global": None},
    )()
    mock_get_profile.return_value = profile

    status = cache_status_for_profile("lab")

    assert set(status["design_content"]) == set(ASSET_KINDS)
    assert set(status["platform_admin"]) == set(ADMIN_SECTIONS)
