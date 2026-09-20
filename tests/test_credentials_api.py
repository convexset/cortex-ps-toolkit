from __future__ import annotations

import json
from pathlib import Path

from cortex_ps_toolkit.credentials import create_profile_from_input, get_profile, update_profile_from_input
from cortex_ps_toolkit.platforms import Platform


def test_create_and_update_profile(tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "credentials.json"
    monkeypatch.setattr(
        "cortex_ps_toolkit.credentials.credentials_collection_path",
        lambda: dest,
    )
    created = create_profile_from_input({
        "label": "Test Lab",
        "url": "https://api-example.crtx.test",
        "key": "secret-key",
        "tenant_type": "xsoar8",
        "api_id": "99",
    })
    assert created.slug == "test-lab"
    assert created.tenant_type == Platform.XSOAR8

    updated = update_profile_from_input("test-lab", {"label": "Test Lab Renamed", "notes": "note"})
    assert updated.label == "Test Lab Renamed"
    assert updated.key == "secret-key"
    profile = get_profile("test-lab")
    assert profile.notes == "note"
