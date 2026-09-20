from __future__ import annotations

from cortex_ps_toolkit.scripts.entity import script_entity_id


def test_script_entity_id_top_level() -> None:
    assert script_entity_id({"id": "abc"}) == "abc"


def test_script_entity_id_commonfields() -> None:
    assert script_entity_id({"commonfields": {"id": "xyz", "version": -1}}) == "xyz"
