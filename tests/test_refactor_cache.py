"""Unit tests for toolkit-cache-only refactor loading."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cortex_ps_toolkit.playbooks.refactor_cache import (
    RefactorCacheMiss,
    bootstrap_playbook_utils_cache_from_toolkit,
    load_toolkit_playbook_body,
    seed_existing_overwrite_targets,
)


@patch("cortex_ps_toolkit.playbooks.refactor_cache.lookup_playbook_body")
@patch("cortex_ps_toolkit.playbooks.refactor_cache.get_profile")
def test_load_toolkit_playbook_body_hit(mock_profile: MagicMock, mock_lookup: MagicMock) -> None:
    mock_profile.return_value = MagicMock(slug="lab")
    mock_lookup.return_value = MagicMock(
        status="hit",
        playbook={"id": "pb-1", "name": "Main"},
        canonical_id="pb-1",
        name="Main",
    )
    body = load_toolkit_playbook_body("lab", playbook_id="pb-1")
    assert body["name"] == "Main"


@patch("cortex_ps_toolkit.playbooks.refactor_cache.lookup_playbook_body")
@patch("cortex_ps_toolkit.playbooks.refactor_cache.get_profile")
def test_load_toolkit_playbook_body_miss(mock_profile: MagicMock, mock_lookup: MagicMock) -> None:
    mock_profile.return_value = MagicMock(slug="lab")
    mock_lookup.return_value = MagicMock(status="missing_file", playbook=None, canonical_id="pb-1", name="")
    with pytest.raises(RefactorCacheMiss):
        load_toolkit_playbook_body("lab", playbook_id="pb-1")


@patch("cortex_ps_toolkit.playbooks.refactor_cache.load_toolkit_playbook_body")
@patch("cortex_ps_toolkit.playbooks.refactor_cache._ensure_imported")
def test_bootstrap_playbook_utils_cache_writes_fresh_meta(
    mock_import: MagicMock,
    mock_load: MagicMock,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import dataclass

    @dataclass
    class CacheMeta:
        url: str
        platform: str
        fetched_at: float
        ttl_seconds: float
        playbook_count: int
        complete: bool = True

        def to_dict(self):
            return {
                "url": self.url,
                "platform": self.platform,
                "fetched_at": self.fetched_at,
                "ttl_seconds": self.ttl_seconds,
                "playbook_count": self.playbook_count,
                "complete": self.complete,
            }

    fake_mod = MagicMock(CacheMeta=CacheMeta)
    monkeypatch.setitem(__import__("sys").modules, "playbook_utils.cache", fake_mod)

    mock_load.return_value = {"id": "pb-1", "name": "Main", "tasks": {}}
    cache = MagicMock()
    cache.credentials.url = "https://example.test"
    cache.credentials.platform.value = "xsoar8"
    cache.ttl_seconds = 3600
    cache._load_index.return_value = {"by_id": {"pb-1": {"id": "pb-1"}}, "by_name": {}}
    cache.meta_path = tmp_path / "meta.json"

    info = bootstrap_playbook_utils_cache_from_toolkit(cache, "lab", "pb-1")

    cache._upsert.assert_called_once()
    assert cache.meta_path.is_file()
    assert info["seeded_playbook_id"] == "pb-1"


def test_seed_existing_overwrite_targets_upserts_index_stubs() -> None:
    cache = MagicMock()
    count = seed_existing_overwrite_targets(
        cache,
        [
            {"name": "Sub A", "playbook_id": "id-a", "role": "sub_playbook"},
            {"name": "Parent", "playbook_id": "", "role": "parent_copy"},
        ],
    )
    assert count == 1
    cache._upsert.assert_called_once()
    payload = cache._upsert.call_args[0][0]
    assert payload["id"] == "id-a"
    assert payload["name"] == "Sub A"
