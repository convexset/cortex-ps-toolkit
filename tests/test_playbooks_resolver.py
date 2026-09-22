from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.playbooks.resolver import CachePlaybookResolver


@patch("cortex_ps_toolkit.playbooks.resolver.save_playbook_body")
@patch("cortex_ps_toolkit.playbooks.resolver.api.get_playbook")
@patch("cortex_ps_toolkit.playbooks.resolver.lookup_playbook_body")
@patch.object(CachePlaybookResolver, "_build_index")
def test_resolver_fetches_playbook_when_body_missing(
    mock_build_index,
    mock_lookup,
    mock_get_playbook,
    mock_save_body,
) -> None:
    profile = MagicMock(slug="bay-xsiam-1")
    mock_get_playbook.return_value = {"id": "pb-id", "name": "Main PB", "tasks": {}}
    mock_lookup.return_value = MagicMock(
        status="missing_file",
        playbook=None,
        canonical_id="pb-id",
        name="Main PB",
        index_meta={"id": "pb-id", "name": "Main PB"},
        restamped_modified=False,
    )

    resolver = CachePlaybookResolver(profile, allow_live_fetch=True)
    loaded = resolver.load("pb-id")

    mock_get_playbook.assert_called_once_with(profile, "pb-id")
    mock_save_body.assert_called_once()
    assert loaded["name"] == "Main PB"


@patch("cortex_ps_toolkit.playbooks.resolver.lookup_playbook_body")
@patch.object(CachePlaybookResolver, "_build_index")
def test_resolver_cache_only_raises_when_body_missing(
    mock_build_index,
    mock_lookup,
) -> None:
    profile = MagicMock(slug="bay-xsiam-1")
    mock_lookup.return_value = MagicMock(
        status="missing_file",
        playbook=None,
        canonical_id="pb-id",
        name="pb-id",
        index_meta=None,
        restamped_modified=False,
    )
    resolver = CachePlaybookResolver(profile, allow_live_fetch=False)

    try:
        resolver.load("pb-id")
    except KeyError as exc:
        assert "Playbook body not cached" in str(exc)
    else:
        raise AssertionError("expected KeyError")
