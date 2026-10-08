"""CLI for extended workflow bundles (copy, export, resolve)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .bundles.copy import copy_bundle_to_tenant, plan_bundle_copy
from .bundles.export import build_bundle_zip_bytes, plan_bundle_export
from .cli_content import add_copy_flags, add_copy_profiles, add_post_copy_diff_flag, print_json, validate_copy_flags
from .content.copy_plan_params import normalize_copy_kwargs
from .design_content.bundle_presets import (
    delete_bundle_preset,
    get_bundle_preset,
    list_bundle_presets,
    resolve_bundle_items,
    save_bundle_preset,
)


def _load_items(path: str) -> list[dict[str, Any]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("items file must be a JSON array")
    return [dict(item) for item in raw]


def _copy_kwargs_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return normalize_copy_kwargs(
        overwrite=bool(args.overwrite),
        stop_on_conflict=bool(args.stop_on_conflict),
        copy_mode=getattr(args, "copy_mode", None),
        rename_suffix=str(getattr(args, "rename_suffix", "") or ""),
        rename_map={},
    )


def register_bundles_cli(sub: argparse._SubParsersAction) -> None:
    bundles = sub.add_parser("bundles", help="Extended workflow bundles (copy, export, resolve)")
    nested = bundles.add_subparsers(dest="bundles_command", required=True)

    resolve = nested.add_parser("resolve", help="Resolve basket items on source tenant")
    resolve.add_argument("--profile", required=True)
    resolve.add_argument("--items-file", required=True, help="JSON array of {asset,id,name}")
    resolve.set_defaults(func=_cmd_resolve)

    copy_preview = nested.add_parser("copy-preview", help="Plan multi-phase bundle copy")
    add_copy_profiles(copy_preview)
    copy_preview.add_argument("--items-file", required=True)
    copy_preview.add_argument("--shallow-playbooks", action=argparse.BooleanOptionalAction, default=True)
    add_copy_flags(copy_preview)
    copy_preview.set_defaults(func=_cmd_copy_preview)

    copy = nested.add_parser("copy", help="Execute multi-phase bundle copy")
    add_copy_profiles(copy)
    copy.add_argument("--items-file", required=True)
    copy.add_argument("--shallow-playbooks", action=argparse.BooleanOptionalAction, default=True)
    add_copy_flags(copy)
    add_post_copy_diff_flag(copy)
    copy.set_defaults(func=_cmd_copy)

    export_preview = nested.add_parser("export-preview", help="Plan portable ZIP export")
    export_preview.add_argument("--profile", required=True, dest="source_profile")
    export_preview.add_argument("--items-file", required=True)
    export_preview.add_argument("--bundle-name", default="")
    export_preview.set_defaults(func=_cmd_export_preview)

    export = nested.add_parser("export", help="Write portable ZIP bundle export")
    export.add_argument("--profile", required=True, dest="source_profile")
    export.add_argument("--items-file", required=True)
    export.add_argument("--output", required=True, help="Output .zip path")
    export.add_argument("--bundle-name", default="")
    export.set_defaults(func=_cmd_export)

    presets = nested.add_parser("presets", help="Saved bundle presets on disk (per source profile)")
    preset_nested = presets.add_subparsers(dest="presets_command", required=True)

    preset_list = preset_nested.add_parser("list", help="List saved presets for a source profile")
    preset_list.add_argument("--profile", required=True, dest="source_profile")
    preset_list.set_defaults(func=_cmd_presets_list)

    preset_get = preset_nested.add_parser("get", help="Show one saved preset (includes items)")
    preset_get.add_argument("--profile", required=True, dest="source_profile")
    preset_get.add_argument("--id", required=True, dest="bundle_id")
    preset_get.set_defaults(func=_cmd_presets_get)

    preset_save = preset_nested.add_parser("save", help="Save or update a preset from items file")
    preset_save.add_argument("--profile", required=True, dest="source_profile")
    preset_save.add_argument("--name", required=True, help="Display name / default id")
    preset_save.add_argument("--items-file", required=True)
    preset_save.add_argument("--id", default="", help="Optional stable bundle id")
    preset_save.set_defaults(func=_cmd_presets_save)

    preset_delete = preset_nested.add_parser("delete", help="Delete a saved preset")
    preset_delete.add_argument("--profile", required=True, dest="source_profile")
    preset_delete.add_argument("--id", required=True, dest="bundle_id")
    preset_delete.set_defaults(func=_cmd_presets_delete)


def _cmd_resolve(args: argparse.Namespace) -> int:
    items = _load_items(args.items_file)
    result = resolve_bundle_items(args.profile, items)
    print_json(result)
    return 0 if not result.get("missing_count") else 1


def _cmd_copy_preview(args: argparse.Namespace) -> int:
    err = validate_copy_flags(overwrite=args.overwrite, stop_on_conflict=args.stop_on_conflict)
    if err:
        return err
    items = _load_items(args.items_file)
    opts = _copy_kwargs_from_args(args)
    plan = plan_bundle_copy(
        args.from_profile,
        args.to_profile,
        items,
        shallow_playbooks=bool(args.shallow_playbooks),
        **opts,
    )
    print_json(plan)
    return 1 if plan.get("would_abort") else 0


def _cmd_copy(args: argparse.Namespace) -> int:
    err = validate_copy_flags(overwrite=args.overwrite, stop_on_conflict=args.stop_on_conflict)
    if err:
        return err
    items = _load_items(args.items_file)
    opts = _copy_kwargs_from_args(args)
    result = copy_bundle_to_tenant(
        args.from_profile,
        args.to_profile,
        items,
        shallow_playbooks=bool(args.shallow_playbooks),
        post_copy_diff=bool(args.post_copy_diff),
        **opts,
    )
    print_json(result)
    if result.get("aborted"):
        return 1
    return 0


def _cmd_export_preview(args: argparse.Namespace) -> int:
    items = _load_items(args.items_file)
    plan = plan_bundle_export(
        args.source_profile,
        items=items,
        bundle_id=None,
    )
    print_json(plan)
    return 0


def _cmd_presets_list(args: argparse.Namespace) -> int:
    rows = list_bundle_presets(source_profile=args.source_profile)
    print_json({"source_profile": args.source_profile, "bundles": rows, "count": len(rows)})
    return 0


def _cmd_presets_get(args: argparse.Namespace) -> int:
    try:
        entry = get_bundle_preset(args.source_profile, args.bundle_id)
    except KeyError:
        print(f"Preset not found: {args.bundle_id!r}", file=sys.stderr)
        return 1
    print_json(entry)
    return 0


def _cmd_presets_save(args: argparse.Namespace) -> int:
    items = _load_items(args.items_file)
    entry = save_bundle_preset(
        name=args.name,
        source_profile=args.source_profile,
        items=items,
        bundle_id=args.id or None,
    )
    print_json(entry)
    return 0


def _cmd_presets_delete(args: argparse.Namespace) -> int:
    if not delete_bundle_preset(args.source_profile, args.bundle_id):
        print(f"Preset not found: {args.bundle_id!r}", file=sys.stderr)
        return 1
    print_json({"deleted": True, "source_profile": args.source_profile, "id": args.bundle_id})
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    items = _load_items(args.items_file)
    zip_bytes, filename = build_bundle_zip_bytes(
        args.source_profile,
        items=items,
        bundle_name=args.bundle_name or None,
    )
    out_path = Path(args.output)
    if out_path.suffix.lower() != ".zip" and not args.output.endswith(".zip"):
        out_path = out_path.with_suffix(".zip")
    out_path.write_bytes(zip_bytes)
    print(f"Wrote {out_path} ({len(zip_bytes)} bytes, suggested name {filename})", file=sys.stderr)
    return 0
