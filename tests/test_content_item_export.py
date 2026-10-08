"""Pack-style contentitemexportablefields helpers."""

from __future__ import annotations

from pathlib import Path

import yaml

from cortex_ps_toolkit.content.content_item_export import content_item_export_block

SAMPLES = Path("/Users/weichen/Downloads/dev/scratch/xsoar-samples")


def test_content_item_block_from_pack_script_export() -> None:
    doc = yaml.safe_load((SAMPLES / "tenant_export__RunPollingCommand.yml").read_text(encoding="utf-8"))
    expected = doc["contentitemexportablefields"]
    block = content_item_export_block(
        {
            "packID": "CommonScripts",
            "packName": "Common Scripts",
            "itemVersion": "1.22.26",
            "fromServerVersion": "5.0.0",
            "toServerVersion": "",
            "definitionId": "",
            "prevName": "",
        },
    )
    assert block is not None
    assert block["contentitemexportablefields"] == expected


def test_content_item_block_missing_when_no_pack_metadata() -> None:
    assert content_item_export_block({"name": "CustomScript"}) is None
