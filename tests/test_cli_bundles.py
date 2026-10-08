"""CLI wiring for bundles subcommands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from unittest.mock import patch

import pytest

from cortex_ps_toolkit.cli_bundles import _cmd_presets_list, _cmd_presets_save, register_bundles_cli
from cortex_ps_toolkit.design_content import bundle_presets as bp


def test_bundles_cli_registers_subcommands(tmp_path: Path) -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    register_bundles_cli(sub)
    items = tmp_path / "items.json"
    items.write_text(json.dumps([{"asset": "scripts", "id": "s1", "name": "s1"}]), encoding="utf-8")
    args = parser.parse_args(
        [
            "bundles",
            "copy-preview",
            "--from-profile",
            "a",
            "--to-profile",
            "b",
            "--items-file",
            str(items),
        ],
    )
    assert args.bundles_command == "copy-preview"
    preset_args = parser.parse_args(["bundles", "presets", "list", "--profile", "lab"])
    assert preset_args.presets_command == "list"


def test_bundles_resolve_items_file_shape(tmp_path: Path) -> None:
    items_path = tmp_path / "items.json"
    items_path.write_text(json.dumps([{"asset": "scripts", "id": "x", "name": "x"}]), encoding="utf-8")
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    register_bundles_cli(sub)
    args = parser.parse_args(["bundles", "resolve", "--profile", "lab", "--items-file", str(items_path)])
    assert args.bundles_command == "resolve"
    assert args.items_file == str(items_path)


@pytest.fixture(autouse=True)
def _isolate_bundles_path(tmp_path, monkeypatch):
    path = tmp_path / "object_setup_bundles.json"
    monkeypatch.setattr(bp, "BUNDLES_PATH", path)
    yield path


@patch("cortex_ps_toolkit.design_content.bundle_presets.get_profile")
def test_cli_presets_save_and_list(mock_profile, tmp_path: Path) -> None:
    mock_profile.return_value.slug = "lab"
    items = tmp_path / "items.json"
    items.write_text(json.dumps([{"asset": "scripts", "id": "s1", "name": "s1"}]), encoding="utf-8")
    save_args = argparse.Namespace(
        source_profile="lab",
        name="Workflow A",
        items_file=str(items),
        id="",
    )
    assert _cmd_presets_save(save_args) == 0
    list_args = argparse.Namespace(source_profile="lab")
    assert _cmd_presets_list(list_args) == 0
