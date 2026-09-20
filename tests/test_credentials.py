from __future__ import annotations

import json
from pathlib import Path

from cortex_ps_toolkit.credentials import import_lab_profiles, list_profiles, slugify_label
from cortex_ps_toolkit.platforms import Platform


def test_slugify_label() -> None:
    assert slugify_label("xsoar-japac-dev") == "xsoar-japac-dev"


def test_import_lab_profiles(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifest"
    manifest_dir.mkdir()
    (manifest_dir / "tenant.json").write_text(
        json.dumps({"url": "https://api-example.crtx.test", "id": 99, "key": "secret-key"}),
        encoding="utf-8",
    )
    sources = [
        {
            "slug": "lab-test",
            "label": "lab-test",
            "tenant_type": "xsoar8",
            "source_file": "tenant.json",
            "notes": "test",
        }
    ]
    dest = tmp_path / "collections" / "credentials.json"
    imported = import_lab_profiles(sources, base_dir=manifest_dir, destination=dest)
    assert len(imported) == 1
    assert imported[0].tenant_type == Platform.XSOAR8
    assert imported[0].api_id == "99"
    assert imported[0].cache_key.endswith("/xsoar8/99")
    profiles = list_profiles(dest)
    assert len(profiles) == 1
    assert profiles[0].to_public_dict()["key_masked"].endswith("…")
