"""Tests for playbook body lookup and analysis stale policy."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from cortex_ps_toolkit.playbooks.body_lookup import lookup_playbook_body, resolve_playbook_ref
from cortex_ps_toolkit.playbooks.cache import save_playbook_body, write_playbooks_cache


@pytest.fixture
def profile(tmp_path, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setenv("CORTEX_PS_DATA_DIR", str(tmp_path / "data"))
    slug = "lab-body-lookup"
    return MagicMock(slug=slug, cache_key=f"host|xsoar8|key1")


def test_resolve_playbook_ref_by_name(profile: MagicMock) -> None:
    write_playbooks_cache(
        profile,
        [{"id": "uuid-1", "name": "Main PB", "modified": "2026-01-01T00:00:00Z"}],
    )
    canonical, meta, name = resolve_playbook_ref(profile, playbook_name="Main PB")
    assert canonical == "uuid-1"
    assert meta is not None
    assert name == "Main PB"


def test_analysis_policy_reuses_body_on_modified_mismatch(profile: MagicMock) -> None:
    write_playbooks_cache(
        profile,
        [{"id": "uuid-1", "name": "Main PB", "modified": "2026-01-02T00:00:00Z"}],
    )
    save_playbook_body(
        profile,
        "uuid-1",
        {"id": "uuid-1", "name": "Main PB", "tasks": {"0": {"type": "start"}}},
    )
    # Simulate older body stamp from before index refresh
    from cortex_ps_toolkit.playbooks.cache import playbook_body_path

    path = playbook_body_path(profile, "uuid-1")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["modified"] = "2026-01-01T00:00:00Z"
    path.write_text(json.dumps(payload), encoding="utf-8")

    lookup = lookup_playbook_body(profile, playbook_id="uuid-1", stale_policy="analysis")
    assert lookup.status == "hit"
    assert lookup.playbook is not None
    assert lookup.restamped_modified is True

    updated = json.loads(path.read_text(encoding="utf-8"))
    assert updated["modified"] == "2026-01-02T00:00:00Z"


def test_strict_policy_rejects_modified_mismatch(profile: MagicMock) -> None:
    write_playbooks_cache(
        profile,
        [{"id": "uuid-1", "name": "Main PB", "modified": "2026-01-02T00:00:00Z"}],
    )
    save_playbook_body(
        profile,
        "uuid-1",
        {"id": "uuid-1", "name": "Main PB", "tasks": {}},
    )
    from cortex_ps_toolkit.playbooks.cache import playbook_body_path

    path = playbook_body_path(profile, "uuid-1")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["modified"] = "2026-01-01T00:00:00Z"
    path.write_text(json.dumps(payload), encoding="utf-8")

    lookup = lookup_playbook_body(profile, playbook_id="uuid-1", stale_policy="strict")
    assert lookup.status == "modified_mismatch"
    assert lookup.playbook is None
