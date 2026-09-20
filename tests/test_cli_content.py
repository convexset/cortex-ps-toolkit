from __future__ import annotations

import argparse

import pytest

from cortex_ps_toolkit.cli import build_parser
from cortex_ps_toolkit.cli_content import validate_copy_flags


def test_validate_copy_flags_rejects_both() -> None:
    assert validate_copy_flags(overwrite=True, stop_on_conflict=True) == 1


def test_validate_copy_flags_ok() -> None:
    assert validate_copy_flags(overwrite=False, stop_on_conflict=False) is None


@pytest.mark.parametrize(
    "argv",
    [
        ["lists", "refresh", "--profile", "lab"],
        ["lists", "copy-preview", "--from-profile", "a", "--to-profile", "b", "--id", "1"],
        ["lists", "delete-preview", "--profile", "lab", "--id", "1", "--id", "2"],
        ["playbooks", "show", "--profile", "lab", "--id", "pb-1"],
        ["scripts", "copy", "--from-profile", "a", "--to-profile", "b", "--id", "s1"],
    ],
)
def test_parser_accepts_content_commands(argv: list[str]) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    assert callable(args.func)


def test_lists_save_subcommand_registered() -> None:
    parser = build_parser()
    args = parser.parse_args(["lists", "save", "--profile", "lab", "--name", "Test", "--data", "x"])
    assert args.name == "Test"
