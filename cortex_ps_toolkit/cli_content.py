"""Shared CLI registration for lists, playbooks, and scripts."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol

CopyPlanFn = Callable[..., dict[str, Any]]
CopyFn = Callable[..., dict[str, Any]]
DeletePlanFn = Callable[[str, list[str]], dict[str, Any]]
DeleteFn = Callable[[str, list[str]], dict[str, Any]]


class ExtraSubcommandRegistrar(Protocol):
    def __call__(self, nested: argparse._SubParsersAction) -> None: ...


def print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2))


def validate_copy_flags(*, overwrite: bool, stop_on_conflict: bool) -> Optional[int]:
    if stop_on_conflict and overwrite:
        print("Error: --overwrite and --stop-on-conflict cannot both be set", file=sys.stderr)
        return 1
    return None


def add_copy_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--overwrite", action="store_true", help="Update if name exists on target")
    parser.add_argument(
        "--stop-on-conflict",
        action="store_true",
        help="Abort if any name already exists on target",
    )


def add_copy_profiles(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from-profile", required=True, dest="from_profile")
    parser.add_argument("--to-profile", required=True, dest="to_profile")


def add_bulk_ids(parser: argparse.ArgumentParser, *, help_text: str) -> None:
    parser.add_argument("--id", action="append", required=True, help=help_text)


@dataclass(frozen=True)
class ContentResourceCli:
    """CLI wiring for one cached content resource (lists, playbooks, scripts)."""

    name: str
    help: str
    id_help: str
    refresh: Callable[[str], dict[str, Any]]
    list_cached: Callable[[str], list[dict[str, Any]]]
    format_row: Callable[[dict[str, Any]], str]
    empty_list_hint: str
    find_by_id: Callable[[str, str], Optional[dict[str, Any]]]
    find_by_name: Callable[[str, str], Optional[dict[str, Any]]]
    plan_copy: CopyPlanFn
    copy: CopyFn
    plan_delete: DeletePlanFn
    delete: DeleteFn


def _cmd_refresh(resource: ContentResourceCli, args: argparse.Namespace) -> int:
    print_json(resource.refresh(args.profile))
    return 0


def _cmd_list(resource: ContentResourceCli, args: argparse.Namespace) -> int:
    items = resource.list_cached(args.profile)
    if not items:
        print(resource.empty_list_hint)
        return 0
    for item in items:
        print(resource.format_row(item))
    print(f"\n{len(items)} {resource.name.rstrip('s')}(s)")
    return 0


def _cmd_show(resource: ContentResourceCli, args: argparse.Namespace) -> int:
    if args.id:
        item = resource.find_by_id(args.profile, args.id)
    elif args.name:
        item = resource.find_by_name(args.profile, args.name)
    else:
        print("Provide --id or --name", file=sys.stderr)
        return 2
    if not item:
        print(f"{resource.name.rstrip('s').title()} not found.", file=sys.stderr)
        return 1
    print_json(item)
    return 0


def _cmd_copy_preview(resource: ContentResourceCli, args: argparse.Namespace) -> int:
    code = validate_copy_flags(overwrite=args.overwrite, stop_on_conflict=args.stop_on_conflict)
    if code is not None:
        return code
    print_json(
        resource.plan_copy(
            args.from_profile,
            args.to_profile,
            args.id,
            overwrite=args.overwrite,
            stop_on_conflict=args.stop_on_conflict,
        )
    )
    return 0


def _cmd_copy(resource: ContentResourceCli, args: argparse.Namespace) -> int:
    code = validate_copy_flags(overwrite=args.overwrite, stop_on_conflict=args.stop_on_conflict)
    if code is not None:
        return code
    print_json(
        resource.copy(
            args.from_profile,
            args.to_profile,
            args.id,
            overwrite=args.overwrite,
            stop_on_conflict=args.stop_on_conflict,
        )
    )
    return 0


def _cmd_delete_preview(resource: ContentResourceCli, args: argparse.Namespace) -> int:
    print_json(resource.plan_delete(args.profile, args.id))
    return 0


def _cmd_delete(resource: ContentResourceCli, args: argparse.Namespace) -> int:
    print_json(resource.delete(args.profile, args.id))
    return 0


def register_content_cli(
    sub: argparse._SubParsersAction,
    resource: ContentResourceCli,
    *,
    register_extra: Optional[ExtraSubcommandRegistrar] = None,
) -> argparse.ArgumentParser:
    """Register refresh, list, show, copy, copy-preview, delete, delete-preview subcommands."""
    parser = sub.add_parser(resource.name, help=resource.help)
    nested = parser.add_subparsers(dest=f"{resource.name}_command", required=True)

    refresh = nested.add_parser("refresh", help=f"Fetch {resource.name} from tenant and update cache")
    refresh.add_argument("--profile", required=True)
    refresh.set_defaults(func=lambda args, r=resource: _cmd_refresh(r, args))

    list_cmd = nested.add_parser("list", help=f"List cached {resource.name}")
    list_cmd.add_argument("--profile", required=True)
    list_cmd.set_defaults(func=lambda args, r=resource: _cmd_list(r, args))

    show = nested.add_parser("show", help=f"Show one cached {resource.name.rstrip('s')} by id or name")
    show.add_argument("--profile", required=True)
    show.add_argument("--id", help=f"{resource.name.rstrip('s').title()} id")
    show.add_argument("--name", help=f"{resource.name.rstrip('s').title()} name")
    show.set_defaults(func=lambda args, r=resource: _cmd_show(r, args))

    copy_preview = nested.add_parser("copy-preview", help="Preview copy to another tenant")
    add_copy_profiles(copy_preview)
    add_bulk_ids(copy_preview, help_text=resource.id_help)
    add_copy_flags(copy_preview)
    copy_preview.set_defaults(func=lambda args, r=resource: _cmd_copy_preview(r, args))

    copy_cmd = nested.add_parser("copy", help=f"Copy {resource.name.rstrip('s')}(s) to another tenant")
    add_copy_profiles(copy_cmd)
    add_bulk_ids(copy_cmd, help_text=resource.id_help)
    add_copy_flags(copy_cmd)
    copy_cmd.set_defaults(func=lambda args, r=resource: _cmd_copy(r, args))

    delete_preview = nested.add_parser("delete-preview", help="Preview delete on tenant")
    delete_preview.add_argument("--profile", required=True)
    add_bulk_ids(delete_preview, help_text=resource.id_help)
    delete_preview.set_defaults(func=lambda args, r=resource: _cmd_delete_preview(r, args))

    delete_cmd = nested.add_parser("delete", help=f"Delete {resource.name.rstrip('s')}(s) on tenant")
    delete_cmd.add_argument("--profile", required=True)
    add_bulk_ids(delete_cmd, help_text=resource.id_help)
    delete_cmd.set_defaults(func=lambda args, r=resource: _cmd_delete(r, args))

    if register_extra is not None:
        register_extra(nested)

    return parser
