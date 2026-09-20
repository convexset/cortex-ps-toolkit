"""CLI for the local integration credential vault."""

from __future__ import annotations

import argparse
import sys

from .cli_content import print_json
from .vault.store import (
    VaultError,
    VaultLocked,
    VaultPassphraseError,
    init_vault,
    list_entries,
    list_wraps,
    lock_vault,
    status,
    unlock_vault,
)


def register_vault_cli(sub: argparse._SubParsersAction) -> None:
    vault = sub.add_parser("vault", help="Local integration credential vault")
    nested = vault.add_subparsers(dest="vault_command", required=True)

    status_cmd = nested.add_parser("status", help="Show vault initialized/unlocked state")
    status_cmd.set_defaults(func=_cmd_status)

    lock_cmd = nested.add_parser("lock", help="Lock the in-process vault session")
    lock_cmd.set_defaults(func=_cmd_lock)

    unlock_cmd = nested.add_parser("unlock", help="Unlock vault with passphrase")
    unlock_cmd.add_argument("--passphrase", required=True)
    unlock_cmd.set_defaults(func=_cmd_unlock)

    init_cmd = nested.add_parser("init", help="Initialize vault with first passphrase wrap")
    init_cmd.add_argument("--passphrase", required=True)
    init_cmd.add_argument("--alias", default="primary")
    init_cmd.set_defaults(func=_cmd_init)

    wraps_cmd = nested.add_parser("wraps", help="List passphrase wrap slot aliases")
    wraps_cmd.set_defaults(func=_cmd_wraps)

    entries_cmd = nested.add_parser("entries", help="List vault entry metadata (vault must be unlocked)")
    entries_cmd.set_defaults(func=_cmd_entries)


def _vault_error(exc: Exception) -> int:
    print(f"Error: {exc}", file=sys.stderr)
    if isinstance(exc, VaultPassphraseError):
        return 1
    if isinstance(exc, VaultLocked):
        return 2
    return 1


def _cmd_status(_args: argparse.Namespace) -> int:
    print_json(status())
    return 0


def _cmd_lock(_args: argparse.Namespace) -> int:
    print_json(lock_vault())
    return 0


def _cmd_unlock(args: argparse.Namespace) -> int:
    try:
        print_json(unlock_vault(args.passphrase))
    except VaultError as exc:
        return _vault_error(exc)
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    try:
        print_json(init_vault(args.passphrase, alias=args.alias))
    except VaultError as exc:
        return _vault_error(exc)
    return 0


def _cmd_wraps(_args: argparse.Namespace) -> int:
    try:
        print_json({"wraps": list_wraps()})
    except VaultError as exc:
        return _vault_error(exc)
    return 0


def _cmd_entries(_args: argparse.Namespace) -> int:
    try:
        print_json({"entries": list_entries()})
    except VaultError as exc:
        return _vault_error(exc)
    return 0
