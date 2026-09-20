from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.cache.query import query_cache


@patch("cortex_ps_toolkit.cache.query.load_scripts_index")
@patch("cortex_ps_toolkit.cache.query.get_profile")
def test_query_cache_filters_system_scripts(mock_get_profile, mock_load_index) -> None:
    profile = type("P", (), {"slug": "lab"})()
    mock_get_profile.return_value = profile
    mock_load_index.return_value = {
        "refreshed_at": "2026-01-01T00:00:00Z",
        "scripts": [
            {"id": "Print", "name": "Print", "system": True},
            {"id": "96549dff-30fc-4ee7-8b22-e5d30eded845", "name": "TEST_Show_Env", "system": False},
        ],
    }

    result = query_cache("lab", "scripts", system=True)
    assert result["count"] == 1
    assert result["matches"][0]["name"] == "Print"

    custom = query_cache("lab", "scripts", copyable=True)
    assert custom["count"] == 1
    assert custom["matches"][0]["name"] == "TEST_Show_Env"
