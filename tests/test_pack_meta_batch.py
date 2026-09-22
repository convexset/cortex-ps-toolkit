"""Tests for batched pack_meta writes during analysis."""

from __future__ import annotations

from unittest.mock import MagicMock

from cortex_ps_toolkit.cache import pack_meta as pm


def test_pack_meta_write_batch_flushes_once(tmp_path, monkeypatch) -> None:
    profile = MagicMock(slug="lab", cache_key="host/xsiam/key1")
    path = tmp_path / "pack_meta.json"
    monkeypatch.setattr(pm, "pack_meta_path", lambda _p: path)
    path.write_text('{"scripts": {}, "playbooks": {}, "updated_at": null}\n', encoding="utf-8")

    with pm.pack_meta_write_batch(profile):
        pm.save_item_meta(profile, kind="scripts", item_id="s1", meta={"copyable": True})
        pm.save_item_meta(profile, kind="scripts", item_id="s2", meta={"copyable": False})
        assert not path.read_text().count("s1")

    text = path.read_text(encoding="utf-8")
    assert "s1" in text
    assert "s2" in text
