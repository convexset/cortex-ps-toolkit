"""CLI for design-time content assets."""

from __future__ import annotations

import argparse
import json
import sys

from .cli_content import add_bulk_ids, add_copy_flags, add_copy_profiles, print_json, validate_copy_flags
from .design_content.copy import copy_assets_to_tenant, plan_asset_copy
from .design_content.delete import delete_assets, plan_asset_delete
from .design_content.orchestrator import execute_cross_tenant_workflow
from .design_content.service import get_item_body, list_cached_items, refresh_all_cache, refresh_asset_cache
from .design_content.types import ASSET_KINDS, AssetKind


def _parse_asset(raw: str) -> AssetKind:
    asset = raw.strip().lower()
    if asset not in ASSET_KINDS:
        raise ValueError(f"asset must be one of: {', '.join(ASSET_KINDS)}")
    return asset  # type: ignore[return-value]


def _add_delete_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", required=True)
    parser.add_argument("--asset", required=True, choices=ASSET_KINDS)
    add_bulk_ids(parser, help_text="Item id")


def _add_copy_args(parser: argparse.ArgumentParser) -> None:
    add_copy_profiles(parser)
    parser.add_argument("--asset", required=True, choices=ASSET_KINDS)
    add_bulk_ids(parser, help_text="Item id")
    add_copy_flags(parser)


def register_design_content_cli(sub: argparse._SubParsersAction) -> None:
    design = sub.add_parser("design-content", help="Design-time content (layouts, fields, types, …)")
    nested = design.add_subparsers(dest="design_command", required=True)

    refresh = nested.add_parser("refresh", help="Refresh design content cache")
    refresh.add_argument("--profile", required=True)
    refresh.add_argument("--asset", choices=ASSET_KINDS, help="Single asset kind (default: all)")
    refresh.set_defaults(func=_cmd_refresh)

    list_cmd = nested.add_parser("list", help="List cached design content items")
    list_cmd.add_argument("--profile", required=True)
    list_cmd.add_argument("--asset", required=True, choices=ASSET_KINDS)
    list_cmd.set_defaults(func=_cmd_list)

    show = nested.add_parser("show", help="Show one cached item body")
    show.add_argument("--profile", required=True)
    show.add_argument("--asset", required=True, choices=ASSET_KINDS)
    show.add_argument("--id", required=True)
    show.set_defaults(func=_cmd_show)

    copy_preview = nested.add_parser("copy-preview", help="Preview design content copy plan")
    _add_copy_args(copy_preview)
    copy_preview.set_defaults(func=_cmd_copy_preview)

    copy_cmd = nested.add_parser("copy", help="Copy design content items to another tenant")
    _add_copy_args(copy_cmd)
    copy_cmd.add_argument(
        "--prefer-direct-on-xsoar6",
        action="store_true",
        default=True,
        help="Use xsoar6 direct import for single-item copy (default: true)",
    )
    copy_cmd.set_defaults(func=_cmd_copy)

    delete_preview = nested.add_parser("delete-preview", help="Preview design content delete plan")
    _add_delete_args(delete_preview)
    delete_preview.set_defaults(func=_cmd_delete_preview)

    delete_cmd = nested.add_parser("delete", help="Delete design content items from tenant")
    _add_delete_args(delete_cmd)
    delete_cmd.set_defaults(func=_cmd_delete)

    orchestrate = nested.add_parser("orchestrate", help="Ordered cross-tenant copy workflow")
    add_copy_profiles(orchestrate)
    orchestrate.add_argument(
        "--selections-json",
        required=True,
        help='JSON object mapping asset kind to id lists, e.g. \'{"layouts":["My Layout"]}\'',
    )
    add_copy_flags(orchestrate)
    orchestrate.add_argument("--include-correlation-rules", action="store_true")
    orchestrate.add_argument("--correlation-rule-name", action="append", dest="correlation_rule_names")
    orchestrate.set_defaults(func=_cmd_orchestrate)


def _cmd_refresh(args: argparse.Namespace) -> int:
    if args.asset:
        print_json(refresh_asset_cache(args.profile, _parse_asset(args.asset)))
    else:
        print_json(refresh_all_cache(args.profile))
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    items = list_cached_items(args.profile, _parse_asset(args.asset))
    if not items:
        print("No cached items — run design-content refresh first.")
        return 0
    for item in items:
        print(f"{item.get('id')}\t{item.get('name') or ''}\t{item.get('type') or ''}")
    print(f"\n{len(items)} item(s)")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    try:
        print_json(get_item_body(args.profile, _parse_asset(args.asset), args.id))
    except KeyError:
        print(f"Item not found: {args.id}", file=sys.stderr)
        return 1
    return 0


def _cmd_copy_preview(args: argparse.Namespace) -> int:
    err = validate_copy_flags(overwrite=args.overwrite, stop_on_conflict=args.stop_on_conflict)
    if err:
        return err
    print_json(plan_asset_copy(
        args.from_profile,
        args.to_profile,
        _parse_asset(args.asset),
        list(args.id or []),
        overwrite=args.overwrite,
        stop_on_conflict=args.stop_on_conflict,
    ))
    return 0


def _cmd_copy(args: argparse.Namespace) -> int:
    err = validate_copy_flags(overwrite=args.overwrite, stop_on_conflict=args.stop_on_conflict)
    if err:
        return err
    print_json(copy_assets_to_tenant(
        args.from_profile,
        args.to_profile,
        _parse_asset(args.asset),
        list(args.id or []),
        overwrite=args.overwrite,
        stop_on_conflict=args.stop_on_conflict,
        prefer_direct_on_xsoar6=args.prefer_direct_on_xsoar6,
    ))
    return 0


def _cmd_delete_preview(args: argparse.Namespace) -> int:
    print_json(plan_asset_delete(args.profile, _parse_asset(args.asset), list(args.id or [])))
    return 0


def _cmd_delete(args: argparse.Namespace) -> int:
    print_json(delete_assets(args.profile, _parse_asset(args.asset), list(args.id or [])))
    return 0


def _cmd_orchestrate(args: argparse.Namespace) -> int:
    err = validate_copy_flags(overwrite=args.overwrite, stop_on_conflict=args.stop_on_conflict)
    if err:
        return err
    selections = json.loads(args.selections_json)
    if not isinstance(selections, dict):
        print("selections-json must be a JSON object", file=sys.stderr)
        return 2
    print_json(execute_cross_tenant_workflow(
        args.from_profile,
        args.to_profile,
        selections,
        overwrite=args.overwrite,
        stop_on_conflict=args.stop_on_conflict,
        include_correlation_rules=args.include_correlation_rules,
        correlation_rule_names=args.correlation_rule_names,
    ))
    return 0
