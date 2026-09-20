"""CLI smoke tests for vault commands."""

from __future__ import annotations

from cortex_ps_toolkit.cli_vault import register_vault_cli


def test_vault_cli_registers_status_command() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    register_vault_cli(sub)
    args = parser.parse_args(["vault", "status"])
    assert args.vault_command == "status"
    assert args.func.__name__ == "_cmd_status"
