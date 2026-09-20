from __future__ import annotations

from cortex_ps_toolkit.scripts.metadata import (
    classify_script_entry,
    is_copyable_script,
    looks_like_uuid,
)


def test_classify_system_script_from_cache() -> None:
    entry = {"id": "Print", "name": "Print", "system": True}
    assert classify_script_entry(entry) == "system"
    assert not is_copyable_script(entry)


def test_classify_custom_uuid_script() -> None:
    entry = {"id": "96549dff-30fc-4ee7-8b22-e5d30eded845", "name": "TEST_Show_Env", "system": False}
    assert classify_script_entry(entry) == "custom"
    assert is_copyable_script(entry)


def test_classify_content_pack_from_document() -> None:
    entry = {"id": "96549dff-30fc-4ee7-8b22-e5d30eded845", "name": "Foo", "system": False}
    document = {"packID": "MyPack", "id": entry["id"]}
    assert classify_script_entry(entry, document=document) == "content_pack"
    assert not is_copyable_script(entry, document=document)


def test_looks_like_uuid() -> None:
    assert looks_like_uuid("96549dff-30fc-4ee7-8b22-e5d30eded845")
    assert not looks_like_uuid("Print")
