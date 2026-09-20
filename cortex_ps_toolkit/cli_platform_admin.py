"""CLI for platform administration APIs."""

from __future__ import annotations

import argparse
import sys

from .cli_content import print_json
from .platform_admin import api as admin_api
from .platform_admin.bioc_copy import copy_biocs_to_tenant
from .platform_admin.indicator_copy import copy_indicators_to_tenant
from .platform_admin.copy import copy_correlation_rules_to_tenant
from .platform_admin.plan import (
    plan_bioc_delete,
    plan_correlation_delete,
    plan_indicator_copy,
    plan_indicator_delete,
)
from .platform_admin.service import list_cached_items, refresh_all_cache, refresh_section_cache
from .platform_admin.types import ADMIN_SECTIONS, AdminSection
from .credentials import get_profile


def _parse_section(raw: str) -> AdminSection:
    section = raw.strip().lower()
    if section not in ADMIN_SECTIONS:
        raise ValueError(f"section must be one of: {', '.join(ADMIN_SECTIONS)}")
    return section  # type: ignore[return-value]


def register_platform_admin_cli(sub: argparse._SubParsersAction) -> None:
    admin = sub.add_parser("platform-admin", help="Platform admin (correlation rules, BIOCs, RBAC, API keys, IOCs)")
    nested = admin.add_subparsers(dest="admin_command", required=True)

    refresh = nested.add_parser("refresh", help="Refresh platform admin cache")
    refresh.add_argument("--profile", required=True)
    refresh.add_argument("--section", choices=ADMIN_SECTIONS, help="Single section (default: all)")
    refresh.set_defaults(func=_cmd_refresh)

    list_cmd = nested.add_parser("list", help="List cached platform admin items")
    list_cmd.add_argument("--profile", required=True)
    list_cmd.add_argument("--section", required=True, choices=ADMIN_SECTIONS)
    list_cmd.set_defaults(func=_cmd_list)

    corr_copy = nested.add_parser("copy-correlation-rules", help="Copy correlation rules to another tenant")
    corr_copy.add_argument("--from-profile", required=True, dest="from_profile")
    corr_copy.add_argument("--to-profile", required=True, dest="to_profile")
    corr_copy.add_argument("--name", action="append", required=True, dest="rule_names")
    corr_copy.add_argument("--overwrite", action="store_true")
    corr_copy.add_argument("--stop-on-conflict", action="store_true")
    corr_copy.set_defaults(func=_cmd_copy_correlation)

    bioc_insert = nested.add_parser("insert-biocs", help="Insert or update BIOCs (xsiam/xdr5)")
    bioc_insert.add_argument("--profile", required=True)
    bioc_insert.add_argument("--file", required=True, help="JSON file with array of BIOC objects")
    bioc_insert.set_defaults(func=_cmd_insert_biocs)

    ioc_copy = nested.add_parser("copy-indicators", help="Copy indicators to another tenant")
    ioc_copy.add_argument("--from-profile", required=True, dest="from_profile")
    ioc_copy.add_argument("--to-profile", required=True, dest="to_profile")
    ioc_copy.add_argument("--id", action="append", required=True, dest="indicator_ids")
    ioc_copy.add_argument("--overwrite", action="store_true")
    ioc_copy.add_argument("--stop-on-conflict", action="store_true")
    ioc_copy.set_defaults(func=_cmd_copy_indicators)

    bioc_copy = nested.add_parser("copy-biocs", help="Copy BIOCs to another tenant")
    bioc_copy.add_argument("--from-profile", required=True, dest="from_profile")
    bioc_copy.add_argument("--to-profile", required=True, dest="to_profile")
    bioc_copy.add_argument("--name", action="append", required=True, dest="bioc_names")
    bioc_copy.add_argument("--overwrite", action="store_true")
    bioc_copy.add_argument("--stop-on-conflict", action="store_true")
    bioc_copy.set_defaults(func=_cmd_copy_biocs)

    bioc_delete = nested.add_parser("delete-biocs", help="Delete BIOCs by name (xsiam/xdr5)")
    bioc_delete.add_argument("--profile", required=True)
    bioc_delete.add_argument("--name", action="append", required=True, dest="names")
    bioc_delete.set_defaults(func=_cmd_delete_biocs)

    bioc_delete_preview = nested.add_parser("delete-biocs-preview", help="Preview BIOC delete")
    bioc_delete_preview.add_argument("--profile", required=True)
    bioc_delete_preview.add_argument("--name", action="append", required=True, dest="names")
    bioc_delete_preview.set_defaults(func=_cmd_delete_biocs_preview)

    corr_delete = nested.add_parser("delete-correlation-rules", help="Delete correlation rules by name")
    corr_delete.add_argument("--profile", required=True)
    corr_delete.add_argument("--name", action="append", required=True, dest="rule_names")
    corr_delete.set_defaults(func=_cmd_delete_correlation)

    corr_delete_preview = nested.add_parser("delete-correlation-rules-preview", help="Preview correlation rule delete")
    corr_delete_preview.add_argument("--profile", required=True)
    corr_delete_preview.add_argument("--name", action="append", required=True, dest="rule_names")
    corr_delete_preview.set_defaults(func=_cmd_delete_correlation_preview)

    ioc_delete = nested.add_parser("delete-indicators", help="Delete indicators by id")
    ioc_delete.add_argument("--profile", required=True)
    ioc_delete.add_argument("--id", action="append", required=True, dest="indicator_ids")
    ioc_delete.set_defaults(func=_cmd_delete_indicators)

    ioc_delete_preview = nested.add_parser("delete-indicators-preview", help="Preview indicator delete")
    ioc_delete_preview.add_argument("--profile", required=True)
    ioc_delete_preview.add_argument("--id", action="append", required=True, dest="indicator_ids")
    ioc_delete_preview.set_defaults(func=_cmd_delete_indicators_preview)

    ioc_copy_preview = nested.add_parser("copy-indicators-preview", help="Preview indicator copy")
    ioc_copy_preview.add_argument("--from-profile", required=True, dest="from_profile")
    ioc_copy_preview.add_argument("--to-profile", required=True, dest="to_profile")
    ioc_copy_preview.add_argument("--id", action="append", required=True, dest="indicator_ids")
    ioc_copy_preview.add_argument("--overwrite", action="store_true")
    ioc_copy_preview.add_argument("--stop-on-conflict", action="store_true")
    ioc_copy_preview.set_defaults(func=_cmd_copy_indicators_preview)


def _cmd_refresh(args: argparse.Namespace) -> int:
    if args.section:
        print_json(refresh_section_cache(args.profile, _parse_section(args.section)))
    else:
        print_json(refresh_all_cache(args.profile))
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    items = list_cached_items(args.profile, _parse_section(args.section))
    if not items:
        print("No cached items — run platform-admin refresh first.")
        return 0
    for item in items:
        print(f"{item.get('id') or item.get('name')}\t{item.get('name') or ''}")
    print(f"\n{len(items)} item(s)")
    return 0


def _cmd_insert_biocs(args: argparse.Namespace) -> int:
    import json
    from pathlib import Path

    path = Path(args.file)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "request_data" in payload:
        biocs = payload["request_data"]
    elif isinstance(payload, list):
        biocs = payload
    else:
        print("Error: --file must contain a JSON array or {\"request_data\": [...]}", file=sys.stderr)
        return 1
    profile = get_profile(args.profile)
    result, status = admin_api.insert_biocs(profile, biocs)
    print_json({"profile": args.profile, "status": status, "result": result})
    refresh_section_cache(args.profile, "biocs")
    return 0


def _cmd_delete_biocs(args: argparse.Namespace) -> int:
    profile = get_profile(args.profile)
    results = admin_api.delete_biocs(profile, list(args.names or []))
    print_json({"profile": args.profile, "results": results})
    refresh_section_cache(args.profile, "biocs")
    return 0


def _cmd_delete_biocs_preview(args: argparse.Namespace) -> int:
    print_json(plan_bioc_delete(args.profile, list(args.names or [])))
    return 0


def _cmd_delete_correlation(args: argparse.Namespace) -> int:
    profile = get_profile(args.profile)
    results = admin_api.delete_correlation_rules(profile, list(args.rule_names or []))
    print_json({"profile": args.profile, "results": results})
    refresh_section_cache(args.profile, "correlation-rules")
    return 0


def _cmd_delete_correlation_preview(args: argparse.Namespace) -> int:
    print_json(plan_correlation_delete(args.profile, list(args.rule_names or [])))
    return 0


def _cmd_delete_indicators(args: argparse.Namespace) -> int:
    profile = get_profile(args.profile)
    result, status = admin_api.delete_indicators(profile, list(args.indicator_ids or []))
    print_json({"profile": args.profile, "status": status, "result": result})
    refresh_section_cache(args.profile, "indicators")
    return 0


def _cmd_delete_indicators_preview(args: argparse.Namespace) -> int:
    print_json(plan_indicator_delete(args.profile, list(args.indicator_ids or [])))
    return 0


def _cmd_copy_indicators_preview(args: argparse.Namespace) -> int:
    if args.overwrite and args.stop_on_conflict:
        print("Error: --overwrite and --stop-on-conflict cannot both be set", file=sys.stderr)
        return 1
    print_json(plan_indicator_copy(
        args.from_profile,
        args.to_profile,
        list(args.indicator_ids or []),
        overwrite=args.overwrite,
        stop_on_conflict=args.stop_on_conflict,
    ))
    return 0


def _cmd_copy_indicators(args: argparse.Namespace) -> int:
    if args.overwrite and args.stop_on_conflict:
        print("Error: --overwrite and --stop-on-conflict cannot both be set", file=sys.stderr)
        return 1
    print_json(copy_indicators_to_tenant(
        args.from_profile,
        args.to_profile,
        list(args.indicator_ids or []),
        overwrite=args.overwrite,
        stop_on_conflict=args.stop_on_conflict,
    ))
    return 0


def _cmd_copy_biocs(args: argparse.Namespace) -> int:
    if args.overwrite and args.stop_on_conflict:
        print("Error: --overwrite and --stop-on-conflict cannot both be set", file=sys.stderr)
        return 1
    print_json(copy_biocs_to_tenant(
        args.from_profile,
        args.to_profile,
        list(args.bioc_names or []),
        overwrite=args.overwrite,
        stop_on_conflict=args.stop_on_conflict,
    ))
    return 0


def _cmd_copy_correlation(args: argparse.Namespace) -> int:
    if args.overwrite and args.stop_on_conflict:
        print("Error: --overwrite and --stop-on-conflict cannot both be set", file=sys.stderr)
        return 1
    print_json(copy_correlation_rules_to_tenant(
        args.from_profile,
        args.to_profile,
        list(args.rule_names or []),
        overwrite=args.overwrite,
        stop_on_conflict=args.stop_on_conflict,
    ))
    return 0
