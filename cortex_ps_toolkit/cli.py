"""CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .cli_design_content import register_design_content_cli
from .cli_platform_admin import register_platform_admin_cli
from .cli_vault import register_vault_cli
from .cli_content import (
    ContentResourceCli,
    add_copy_flags,
    add_copy_profiles,
    print_json,
    register_content_cli,
    validate_copy_flags,
)
from .credentials import (
    get_profile,
    import_lab_profiles,
    list_profiles,
    parse_expiry,
    purge_expired_profiles,
    remove_profile,
    set_profile_expiry,
    set_profile_verify_ssl,
)
from .cache.query import query_cache, query_cache_many
from .lists.cache import find_list_in_index
from .lists.copy import copy_lists_to_tenant, plan_lists_copy
from .lists.delete import delete_lists, plan_lists_delete
from .lists.service import get_list_by_name, list_cached_lists, refresh_lists_cache, save_list
from .paths import credentials_collection_path, package_root
from .playbooks.cache import find_playbook_in_index
from .playbooks.analysis import analyze_playbook
from .playbooks.copy import copy_playbooks_to_tenant, plan_playbooks_copy
from .content.cross_tenant_probe import (
    compare_deep_copy_fidelity,
    lab_trial_targets,
    run_deep_copy_trial,
    run_trial_series,
)
from .playbooks.copy_components import copy_playbook_components_to_tenant, plan_playbook_components_copy
from .playbooks.delete import delete_playbooks, plan_playbooks_delete
from .playbooks.service import get_playbook_by_name, list_cached_playbooks, refresh_playbooks_cache
from .scripts.cache import find_script_in_index
from .scripts.copy import copy_scripts_to_tenant, plan_scripts_copy
from .scripts.delete import delete_scripts, plan_scripts_delete
from .scripts.metadata import describe_script
from .scripts.service import get_script_by_name, list_cached_scripts, refresh_scripts_cache
from .integrations.copy import copy_integrations_to_tenant, plan_integrations_copy
from .integrations.delete import delete_integrations, plan_integrations_delete
from .integrations.service import (
    find_configuration_in_cache,
    get_integration_by_name,
    list_cached_integration_configurations,
    refresh_integrations_cache,
)
from .serve import main as serve_main
from .platforms import Platform, format_operations_table, get_operation, parse_platform
from .xql.service import run_xql_query


def _auto_purge_expired() -> list[str]:
    removed = purge_expired_profiles()
    return [profile.slug for profile in removed]


def _format_expiry(public: dict[str, object]) -> str:
    expires = public.get("expires_at")
    if not expires:
        return ""
    suffix = " EXPIRED" if public.get("expired") else ""
    return f" expires={expires}{suffix}"


def _format_tls(public: dict[str, object]) -> str:
    if public.get("verify_ssl") is False:
        return " tls=skip"
    return ""


def _cmd_credentials_list(args: argparse.Namespace) -> int:
    if not args.include_expired:
        removed = _auto_purge_expired()
        for slug in removed:
            print(f"Purged expired profile: {slug}")
    profiles = list_profiles(include_expired=args.include_expired)
    if not profiles:
        print("No credential profiles. Run: python -m cortex_ps_toolkit credentials import-lab")
        return 0
    for profile in profiles:
        public = profile.to_public_dict()
        print(
            f"{public['slug']:<22} {public['tenant_type']:<8} {public['api_id']:<6} "
            f"{public['url']}{_format_expiry(public)}{_format_tls(public)}  cache={public['cache_key']}"
        )
    return 0


def _cmd_credentials_show(args: argparse.Namespace) -> int:
    profile = get_profile(args.profile)
    print(json.dumps(profile.to_public_dict(), indent=2))
    return 0


def _cmd_credentials_import_lab(_: argparse.Namespace) -> int:
    manifest = package_root() / "presets" / "credentials" / "lab-sources.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    sources = payload.get("sources") or []
    removed = _auto_purge_expired()
    for slug in removed:
        print(f"Purged expired profile: {slug}")
    imported = import_lab_profiles(sources, base_dir=manifest.parent)
    print(f"Imported {len(imported)} profile(s) → {credentials_collection_path()}")
    for profile in imported:
        expiry = f" expires={profile.expires_at}" if profile.expires_at else ""
        print(f"  {profile.slug} ({profile.tenant_type.value}) api_id={profile.api_id}{expiry}")
    return 0


def _cmd_credentials_remove(args: argparse.Namespace) -> int:
    removed = remove_profile(args.profile)
    print(f"Removed profile {removed.slug} and cache at {removed.cache_key}")
    return 0


def _cmd_credentials_expiry_set(args: argparse.Namespace) -> int:
    expires_at = parse_expiry(args.expires)
    profile = set_profile_expiry(args.profile, expires_at)
    print(json.dumps(profile.to_public_dict(), indent=2))
    return 0


def _cmd_credentials_expiry_clear(args: argparse.Namespace) -> int:
    profile = set_profile_expiry(args.profile, None)
    print(json.dumps(profile.to_public_dict(), indent=2))
    return 0


def _cmd_credentials_verify_ssl_set(args: argparse.Namespace) -> int:
    profile = set_profile_verify_ssl(args.profile, args.verify_ssl)
    print(json.dumps(profile.to_public_dict(), indent=2))
    return 0


def _cmd_credentials_purge_expired(args: argparse.Namespace) -> int:
    removed = purge_expired_profiles(dry_run=args.dry_run)
    if not removed:
        print("No expired credential profiles.")
        return 0
    action = "Would purge" if args.dry_run else "Purged"
    for profile in removed:
        print(f"{action}: {profile.slug} (expired {profile.expires_at})")
    return 0


def _cmd_lists_save(args: argparse.Namespace) -> int:
    data = args.data
    if args.data_file:
        data = Path(args.data_file).read_text(encoding="utf-8")
    saved, status_code = save_list(
        args.profile,
        name=args.name,
        data=data,
        list_type=args.type,
        description=args.description,
        list_id=args.id,
    )
    print_json({"status_code": status_code, **saved})
    return 0


def _cmd_xql_run(args: argparse.Namespace) -> int:
    query = args.query
    if args.query_file:
        query = Path(args.query_file).read_text(encoding="utf-8")
    if not query or not query.strip():
        print("Provide --query or --query-file", file=sys.stderr)
        return 2
    result = run_xql_query(
        args.profile,
        query=query.strip(),
        timeframe={"relativeTime": int(args.timeframe_hours) * 3_600_000},
    )
    rows = result.get("rows") or []
    limit = max(1, int(args.limit_rows))
    for row in rows[:limit]:
        print(json.dumps(row, sort_keys=True))
    if len(rows) > limit:
        print(f"... {len(rows) - limit} more row(s) omitted (use --limit-rows)", file=sys.stderr)
    print_json({
        "profile": result.get("profile"),
        "query_id": result.get("query_id"),
        "row_count": result.get("row_count"),
        "elapsed_ms": result.get("elapsed_ms"),
    })
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    argv = ["serve", "--host", args.host, "--port", str(args.port)]
    if args.reload:
        argv.append("--reload")
    if args.debug:
        argv.append("--debug")
    return serve_main(argv[1:])


def _cmd_platforms_list(args: argparse.Namespace) -> int:
    if args.docs:
        for platform in Platform:
            print(f"{platform.value:<10} {platform.label():<20} {platform.doc_overview_url()}")
        return 0
    platforms = [parse_platform(args.platform)] if args.platform else None
    print(format_operations_table(platforms))
    return 0


def _cmd_platforms_show(args: argparse.Namespace) -> int:
    spec = get_operation(args.operation)
    print_json({
        "operation_id": spec.operation_id,
        "name": spec.name,
        "notes": spec.notes,
        "documented": sorted(item.value for item in spec.documented),
        "experimental": sorted(item.value for item in spec.experimental),
    })
    return 0


def _cmd_playbooks_analyze(args: argparse.Namespace) -> int:
    print_json(analyze_playbook(args.profile, args.id))
    return 0


def _playbook_ref_target_args(parser: argparse.ArgumentParser) -> None:
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--id", help="Playbook id")
    target.add_argument("--name", help="Playbook name (resolved from tenant cache)")


def _cmd_playbooks_refactor_preview(args: argparse.Namespace) -> int:
    from .playbooks.refactor import plan_refactor

    payload = plan_refactor(
        args.profile,
        playbook_id=args.id,
        playbook_name=args.name,
        leaf_tasks=args.task or [],
        clusters=args.cluster or [],
        post_task_updates=args.post_task_update or [],
        parent_copy_name=args.parent_copy_name,
        force=args.force,
    )
    print_json(payload)
    return 0 if payload.get("ok") else 2


def _cmd_playbooks_refactor_execute(args: argparse.Namespace) -> int:
    from .playbooks.refactor import execute_refactor

    payload = execute_refactor(
        args.profile,
        playbook_id=args.id,
        playbook_name=args.name,
        leaf_tasks=args.task or [],
        clusters=args.cluster or [],
        post_task_updates=args.post_task_update or [],
        parent_copy_name=args.parent_copy_name,
        damp_run=args.damp_run,
        upload_only=args.upload_only,
        upload_parent_on_mismatch=args.upload_parent_on_mismatch,
        require_match=args.require_match,
        force=args.force,
    )
    print_json(payload)
    return int(payload.get("exit_code") or (0 if payload.get("ok") else 2))


def _cmd_playbooks_update_tasks_preview(args: argparse.Namespace) -> int:
    from .playbooks.refactor import plan_task_updates

    payload = plan_task_updates(
        args.profile,
        playbook=args.playbook,
        name_prefix=args.name_prefix,
        updates=args.update or [],
        context_updates=args.context_update or [],
        match_task_names=args.match_task_name or [],
        match_update=args.match_update,
        force=args.force,
    )
    print_json(payload)
    return 0 if payload.get("ok") else 2


def _cmd_playbooks_update_tasks(args: argparse.Namespace) -> int:
    from .playbooks.refactor import execute_task_updates

    payload = execute_task_updates(
        args.profile,
        playbook=args.playbook,
        name_prefix=args.name_prefix,
        updates=args.update or [],
        context_updates=args.context_update or [],
        match_task_names=args.match_task_name or [],
        match_update=args.match_update,
        dry_run=args.dry_run,
        force=args.force,
    )
    print_json(payload)
    return int(payload.get("exit_code") or (0 if payload.get("ok") else 2))


def _cmd_playbooks_copy_components_preview(args: argparse.Namespace) -> int:
    code = validate_copy_flags(overwrite=args.overwrite, stop_on_conflict=args.stop_on_conflict)
    if code is not None:
        return code
    print_json(
        plan_playbook_components_copy(
            args.from_profile,
            args.to_profile,
            args.id,
            overwrite=args.overwrite,
            stop_on_conflict=args.stop_on_conflict,
        )
    )
    return 0


def _cmd_playbooks_copy_components(args: argparse.Namespace) -> int:
    code = validate_copy_flags(overwrite=args.overwrite, stop_on_conflict=args.stop_on_conflict)
    if code is not None:
        return code
    print_json(
        copy_playbook_components_to_tenant(
            args.from_profile,
            args.to_profile,
            args.id,
            overwrite=args.overwrite,
            stop_on_conflict=args.stop_on_conflict,
        )
    )
    return 0


def _resolve_playbook_id(profile: str, playbook_id: str | None, playbook_name: str | None) -> str:
    if playbook_id:
        return playbook_id
    if not playbook_name:
        raise ValueError("Provide --id or --name")
    entry = find_playbook_in_index(get_profile(profile), name=playbook_name)
    if not entry or not entry.get("id"):
        raise KeyError(f"Playbook {playbook_name!r} not found in cache for {profile}")
    return str(entry["id"])


def _cmd_playbooks_copy_components_trial(args: argparse.Namespace) -> int:
    code = validate_copy_flags(overwrite=args.overwrite, stop_on_conflict=args.stop_on_conflict)
    if code is not None:
        return code
    if not args.to_profile and not args.targets and not args.lab_targets:
        print("Provide --to-profile, --targets, or --lab-targets", file=sys.stderr)
        return 2
    playbook_id = _resolve_playbook_id(args.from_profile, args.id, args.name)
    if args.to_profile:
        result = run_deep_copy_trial(
            args.from_profile,
            args.to_profile,
            playbook_id,
            overwrite=args.overwrite,
            stop_on_conflict=args.stop_on_conflict,
        )
    else:
        if args.lab_targets:
            targets = lab_trial_targets(args.from_profile)
        else:
            targets = [item.strip() for item in args.targets.split(",") if item.strip()]
        result = run_trial_series(
            args.from_profile,
            playbook_id,
            targets,
            overwrite=args.overwrite,
        )
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print_json(result)
    return 0


def _cmd_playbooks_compare_fidelity(args: argparse.Namespace) -> int:
    playbook_id = _resolve_playbook_id(args.from_profile, args.id, args.name)
    print_json(
        compare_deep_copy_fidelity(
            args.from_profile,
            args.to_profile,
            playbook_id,
        )
    )
    return 0


def _parse_optional_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in ("true", "1", "yes", "y"):
        return True
    if lowered in ("false", "0", "no", "n"):
        return False
    raise argparse.ArgumentTypeError(f"Expected true/false, got {value!r}")


def _cmd_cache_query(args: argparse.Namespace) -> int:
    profiles = args.profile or []
    filters = {
        "name": args.name,
        "script_id": args.script_id,
        "playbook_id": args.playbook_id,
        "list_id": args.list_id,
        "system": args.system,
        "origin": args.origin,
        "copyable": args.copyable,
        "id_pattern": args.id_pattern,
        "limit": args.limit,
        "load_script_documents": args.load_documents,
    }
    if len(profiles) == 1:
        print_json(query_cache(profiles[0], args.scope, **filters))
    else:
        print_json(query_cache_many(profiles, args.scope, **filters))
    return 0


def _cmd_scripts_describe(args: argparse.Namespace) -> int:
    if not args.id and not args.name:
        print("Provide --id or --name", file=sys.stderr)
        return 2
    print_json(
        describe_script(
            args.profile,
            script_id=args.id,
            name=args.name,
            load_document=args.load_document,
        )
    )
    return 0


def _cmd_paths(_: argparse.Namespace) -> int:
    from .paths import data_dir

    print_json({
        "package_root": str(package_root()),
        "data_dir": str(data_dir()),
        "credentials_collection": str(credentials_collection_path()),
    })
    return 0


def _find_list_by_id(profile: str, list_id: str):
    return find_list_in_index(get_profile(profile), list_id=list_id)


def _format_list_row(item: dict) -> str:
    return f"{item.get('id', ''):<28} {item.get('type', ''):<12} {item.get('name', '')}"


def _format_playbook_row(item: dict) -> str:
    system = "sys" if item.get("system") else ""
    return f"{item.get('id', ''):<36} {system:<4} {item.get('name', '')}"


def _format_script_row(item: dict) -> str:
    system = "sys" if item.get("system") else ""
    script_type = str(item.get("scriptType") or "")
    return f"{item.get('id', ''):<36} {script_type:<12} {system:<4} {item.get('name', '')}"


def _format_integration_row(item: dict) -> str:
    system = "sys" if item.get("system") else ""
    script = "yes" if item.get("has_script") else "no"
    instances = item.get("instance_count", 0)
    return (
        f"{item.get('name', ''):<28} {str(item.get('display', '')):<24} "
        f"inst={instances:<3} script={script:<3} {system}"
    )


LISTS_CLI = ContentResourceCli(
    name="lists",
    help="XSOAR Lists cache, CRUD, copy, and delete",
    id_help="List id (repeatable)",
    refresh=refresh_lists_cache,
    list_cached=list_cached_lists,
    format_row=_format_list_row,
    empty_list_hint="No cached lists. Run: python -m cortex_ps_toolkit lists refresh --profile <slug>",
    find_by_id=_find_list_by_id,
    find_by_name=get_list_by_name,
    plan_copy=plan_lists_copy,
    copy=copy_lists_to_tenant,
    plan_delete=plan_lists_delete,
    delete=delete_lists,
)

PLAYBOOKS_CLI = ContentResourceCli(
    name="playbooks",
    help="Playbook cache, copy, and delete",
    id_help="Playbook id (repeatable)",
    refresh=refresh_playbooks_cache,
    list_cached=list_cached_playbooks,
    format_row=_format_playbook_row,
    empty_list_hint="No cached playbooks. Run: python -m cortex_ps_toolkit playbooks refresh --profile <slug>",
    find_by_id=lambda profile, item_id: find_playbook_in_index(get_profile(profile), playbook_id=item_id),
    find_by_name=get_playbook_by_name,
    plan_copy=plan_playbooks_copy,
    copy=copy_playbooks_to_tenant,
    plan_delete=plan_playbooks_delete,
    delete=delete_playbooks,
)

SCRIPTS_CLI = ContentResourceCli(
    name="scripts",
    help="Automation script cache, copy, and delete",
    id_help="Script id (repeatable)",
    refresh=refresh_scripts_cache,
    list_cached=list_cached_scripts,
    format_row=_format_script_row,
    empty_list_hint="No cached scripts. Run: python -m cortex_ps_toolkit scripts refresh --profile <slug>",
    find_by_id=lambda profile, item_id: find_script_in_index(get_profile(profile), script_id=item_id),
    find_by_name=get_script_by_name,
    plan_copy=plan_scripts_copy,
    copy=copy_scripts_to_tenant,
    plan_delete=plan_scripts_delete,
    delete=delete_scripts,
)

INTEGRATIONS_CLI = ContentResourceCli(
    name="integrations",
    help="Integration definitions cache, copy, and delete",
    id_help="Integration id or name (repeatable)",
    refresh=refresh_integrations_cache,
    list_cached=list_cached_integration_configurations,
    format_row=_format_integration_row,
    empty_list_hint=(
        "No cached integration definitions. Run: "
        "python -m cortex_ps_toolkit integrations refresh --profile <slug>"
    ),
    find_by_id=find_configuration_in_cache,
    find_by_name=get_integration_by_name,
    plan_copy=plan_integrations_copy,
    copy=copy_integrations_to_tenant,
    plan_delete=plan_integrations_delete,
    delete=delete_integrations,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cortex_ps_toolkit")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    paths = sub.add_parser("paths", help="Show resolved data paths")
    paths.set_defaults(func=_cmd_paths)

    creds = sub.add_parser("credentials", help="Credential profile management")
    cred_sub = creds.add_subparsers(dest="cred_command", required=True)

    cred_list = cred_sub.add_parser("list", help="List credential profiles (auto-purges expired)")
    cred_list.add_argument(
        "--include-expired",
        action="store_true",
        help="Show expired profiles without purging them",
    )
    cred_list.set_defaults(func=_cmd_credentials_list)

    cred_show = cred_sub.add_parser("show", help="Show one profile (masked key)")
    cred_show.add_argument("--profile", required=True)
    cred_show.set_defaults(func=_cmd_credentials_show)

    cred_import = cred_sub.add_parser("import-lab", help="Import lab profiles from bay/*.json sources")
    cred_import.set_defaults(func=_cmd_credentials_import_lab)

    cred_remove = cred_sub.add_parser("remove", help="Remove a profile and its cache directory")
    cred_remove.add_argument("--profile", required=True)
    cred_remove.set_defaults(func=_cmd_credentials_remove)

    cred_purge = cred_sub.add_parser("purge-expired", help="Remove expired profiles and their caches")
    cred_purge.add_argument("--dry-run", action="store_true")
    cred_purge.set_defaults(func=_cmd_credentials_purge_expired)

    cred_expiry = cred_sub.add_parser("expiry", help="Set or clear credential expiry")
    expiry_sub = cred_expiry.add_subparsers(dest="expiry_command", required=True)

    expiry_set = expiry_sub.add_parser("set", help="Set expiry (ISO date or 'end Nov 2026')")
    expiry_set.add_argument("--profile", required=True)
    expiry_set.add_argument("--expires", required=True, help="e.g. 2026-11-30 or 'end Nov 2026'")
    expiry_set.set_defaults(func=_cmd_credentials_expiry_set)

    expiry_clear = expiry_sub.add_parser("clear", help="Remove expiry from a profile")
    expiry_clear.add_argument("--profile", required=True)
    expiry_clear.set_defaults(func=_cmd_credentials_expiry_clear)

    cred_verify = cred_sub.add_parser("verify-ssl", help="Control TLS certificate verification per profile")
    verify_sub = cred_verify.add_subparsers(dest="verify_command", required=True)

    verify_set = verify_sub.add_parser("set", help="Enable or disable TLS verification")
    verify_set.add_argument("--profile", required=True)
    verify_group = verify_set.add_mutually_exclusive_group(required=True)
    verify_group.add_argument("--verify", action="store_true", dest="verify_ssl", help="Require valid TLS cert")
    verify_group.add_argument("--skip", action="store_false", dest="verify_ssl", help="Skip TLS cert verification")
    verify_set.set_defaults(func=_cmd_credentials_verify_ssl_set)

    def _register_lists_save(nested: argparse._SubParsersAction) -> None:
        lists_save = nested.add_parser("save", help="Create or update a list on the tenant")
        lists_save.add_argument("--profile", required=True)
        lists_save.add_argument("--name", required=True)
        lists_save.add_argument("--data", help="List body text")
        lists_save.add_argument("--data-file", help="Read list body from file")
        lists_save.add_argument("--type", default="plain_text", dest="type")
        lists_save.add_argument("--description", default="")
        lists_save.add_argument("--id", help="Existing list id to update")
        lists_save.set_defaults(func=_cmd_lists_save)

    def _register_playbooks_extra(nested: argparse._SubParsersAction) -> None:
        analyze = nested.add_parser("analyze", help="Analyze playbook structure, tasks, scripts, and commands")
        analyze.add_argument("--profile", required=True)
        analyze.add_argument("--id", required=True, help="Root playbook id")
        analyze.set_defaults(func=_cmd_playbooks_analyze)

        refactor_preview = nested.add_parser(
            "refactor-preview",
            help="Preflight leaf/cluster refactor (no tenant uploads)",
        )
        refactor_preview.add_argument("--profile", required=True)
        _playbook_ref_target_args(refactor_preview)
        refactor_preview.add_argument(
            "--task",
            action="append",
            help="Leaf extract task id or name (repeatable)",
        )
        refactor_preview.add_argument(
            "--cluster",
            action="append",
            metavar="START:END",
            help="Cluster extract START:END (repeatable)",
        )
        refactor_preview.add_argument(
            "--post-task-update",
            action="append",
            metavar="MATCH|actions",
            help="Post-refactor error-handling update on generated subs (repeatable)",
        )
        refactor_preview.add_argument("--parent-copy-name")
        refactor_preview.add_argument("--force", action="store_true")
        refactor_preview.set_defaults(func=_cmd_playbooks_refactor_preview)

        refactor_run = nested.add_parser(
            "refactor",
            help="Run extract-multi refactor (subs, compare, descriptions, parent copy)",
        )
        refactor_run.add_argument("--profile", required=True)
        _playbook_ref_target_args(refactor_run)
        refactor_run.add_argument("--task", action="append")
        refactor_run.add_argument("--cluster", action="append", metavar="START:END")
        refactor_run.add_argument("--post-task-update", action="append", metavar="MATCH|actions")
        refactor_run.add_argument("--parent-copy-name")
        refactor_run.add_argument("--damp-run", action="store_true")
        refactor_run.add_argument("--upload-only", action="store_true")
        refactor_run.add_argument("--upload-parent-on-mismatch", action="store_true")
        refactor_run.add_argument("--require-match", action="store_true")
        refactor_run.add_argument("--force", action="store_true")
        refactor_run.set_defaults(func=_cmd_playbooks_refactor_execute)

        update_preview = nested.add_parser(
            "update-tasks-preview",
            help="Preflight in-place task error-handling / context updates",
        )
        update_preview.add_argument("--profile", required=True)
        update_preview.add_argument("--playbook", help="Playbook id or name")
        update_preview.add_argument("--name-prefix", help="Update all playbooks whose name starts with prefix")
        update_preview.add_argument("--update", action="append", metavar="TASK:actions", help="e.g. 8:retry=15x45")
        update_preview.add_argument("--context-update", action="append", metavar="TASK:scope")
        update_preview.add_argument("--match-task-name", action="append", metavar="MATCH")
        update_preview.add_argument("--match-update", help="Actions applied to --match-task-name hits")
        update_preview.add_argument("--force", action="store_true")
        update_preview.set_defaults(func=_cmd_playbooks_update_tasks_preview)

        update_run = nested.add_parser(
            "update-tasks",
            help="Apply in-place task error-handling / context sharing updates",
        )
        update_run.add_argument("--profile", required=True)
        update_run.add_argument("--playbook", help="Playbook id or name")
        update_run.add_argument("--name-prefix")
        update_run.add_argument("--update", action="append", metavar="TASK:actions")
        update_run.add_argument("--context-update", action="append", metavar="TASK:scope")
        update_run.add_argument("--match-task-name", action="append", metavar="MATCH")
        update_run.add_argument("--match-update")
        update_run.add_argument("--dry-run", action="store_true")
        update_run.add_argument("--force", action="store_true")
        update_run.set_defaults(func=_cmd_playbooks_update_tasks)

        comp_preview = nested.add_parser(
            "copy-components-preview",
            help="Preview copy of playbook + sub-playbooks + referenced scripts",
        )
        add_copy_profiles(comp_preview)
        comp_preview.add_argument("--id", required=True, help="Root playbook id")
        add_copy_flags(comp_preview)
        comp_preview.set_defaults(func=_cmd_playbooks_copy_components_preview)

        comp_copy = nested.add_parser(
            "copy-components",
            help="Copy playbook + sub-playbooks + referenced scripts to another tenant",
        )
        add_copy_profiles(comp_copy)
        comp_copy.add_argument("--id", required=True, help="Root playbook id")
        add_copy_flags(comp_copy)
        comp_copy.set_defaults(func=_cmd_playbooks_copy_components)

        comp_trial = nested.add_parser(
            "copy-components-trial",
            help="Deep copy to target(s) and compare fidelity after upload",
        )
        comp_trial.add_argument("--from-profile", required=True, dest="from_profile")
        comp_trial.add_argument("--to-profile", dest="to_profile", help="Single target profile slug")
        comp_trial.add_argument("--id", help="Root playbook id")
        comp_trial.add_argument("--name", help="Root playbook name (resolved from source cache)")
        comp_trial.add_argument(
            "--targets",
            help="Comma-separated target profile slugs (use instead of --to-profile)",
        )
        comp_trial.add_argument(
            "--lab-targets",
            action="store_true",
            help="Copy to all lab tenants except source (excludes bay-xsiam-*, mfec-uat)",
        )
        comp_trial.add_argument(
            "--output",
            help="Write JSON report to this path",
        )
        add_copy_flags(comp_trial)
        comp_trial.set_defaults(func=_cmd_playbooks_copy_components_trial)

        compare = nested.add_parser(
            "compare-fidelity",
            help="Compare existing copied playbooks/scripts on target against source",
        )
        compare.add_argument("--from-profile", required=True, dest="from_profile")
        compare.add_argument("--to-profile", required=True, dest="to_profile")
        compare.add_argument("--id", help="Root playbook id")
        compare.add_argument("--name", help="Root playbook name (resolved from source cache)")
        compare.set_defaults(func=_cmd_playbooks_compare_fidelity)

    def _register_scripts_extra(nested: argparse._SubParsersAction) -> None:
        describe = nested.add_parser(
            "describe",
            help="Describe script origin (system/content-pack/custom) from cache",
        )
        describe.add_argument("--profile", required=True)
        describe.add_argument("--id", help="Script id")
        describe.add_argument("--name", help="Script name")
        describe.add_argument(
            "--load-document",
            action="store_true",
            help="Load full script from tenant API (includes packID/packName)",
        )
        describe.set_defaults(func=_cmd_scripts_describe)

    cache = sub.add_parser("cache", help="Query cached tenant content indexes")
    cache_sub = cache.add_subparsers(dest="cache_command", required=True)

    cache_query = cache_sub.add_parser("query", help="Filter scripts/playbooks/lists in tenant cache")
    cache_query.add_argument(
        "--profile",
        action="append",
        required=True,
        help="Profile slug (repeat for cross-tenant comparison)",
    )
    cache_query.add_argument(
        "--scope",
        required=True,
        choices=["scripts", "playbooks", "lists"],
    )
    cache_query.add_argument("--name", help="Name substring or glob (* ?)")
    cache_query.add_argument("--script-id", dest="script_id")
    cache_query.add_argument("--playbook-id", dest="playbook_id")
    cache_query.add_argument("--list-id", dest="list_id")
    cache_query.add_argument("--system", type=_parse_optional_bool, help="Filter system=true/false")
    cache_query.add_argument(
        "--origin",
        choices=["system", "content_pack", "custom"],
        help="Script origin (loads document when set)",
    )
    cache_query.add_argument("--copyable", type=_parse_optional_bool, help="Filter copyable scripts")
    cache_query.add_argument("--id-pattern", help="Regex applied to item id")
    cache_query.add_argument("--limit", type=int)
    cache_query.add_argument(
        "--load-documents",
        action="store_true",
        help="Load full script documents (pack metadata)",
    )
    cache_query.set_defaults(func=_cmd_cache_query)

    register_content_cli(sub, LISTS_CLI, register_extra=_register_lists_save)
    register_content_cli(sub, PLAYBOOKS_CLI, register_extra=_register_playbooks_extra)
    register_content_cli(sub, SCRIPTS_CLI, register_extra=_register_scripts_extra)
    register_content_cli(sub, INTEGRATIONS_CLI)
    register_design_content_cli(sub)
    register_platform_admin_cli(sub)
    register_vault_cli(sub)

    xql = sub.add_parser("xql", help="Run XQL queries on XSIAM/XDR tenants")
    xql_sub = xql.add_subparsers(dest="xql_command", required=True)

    xql_run = xql_sub.add_parser("run", help="Start query, poll, and return rows")
    xql_run.add_argument("--profile", required=True)
    xql_run.add_argument("--query", help="XQL query text")
    xql_run.add_argument("--query-file", help="Read query from file")
    xql_run.add_argument("--timeframe-hours", type=int, default=24, help="Relative timeframe in hours")
    xql_run.add_argument("--limit-rows", type=int, default=100, help="Max rows to print")
    xql_run.set_defaults(func=_cmd_xql_run)

    serve = sub.add_parser("serve", help="Start local web UI (default :8770)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8770)
    serve.add_argument("--reload", action="store_true")
    serve.add_argument("--debug", action="store_true")
    serve.set_defaults(func=_cmd_serve)

    platforms = sub.add_parser("platforms", help="Platform docs and operation support matrix")
    plat_sub = platforms.add_subparsers(dest="plat_command", required=True)

    plat_list = plat_sub.add_parser("list", help="Operation support matrix")
    plat_list.add_argument("--platform", help="Filter columns to one platform (e.g. xsiam)")
    plat_list.add_argument("--docs", action="store_true", help="List platform overview doc URLs")
    plat_list.set_defaults(func=_cmd_platforms_list)

    plat_show = plat_sub.add_parser("show", help="Show one operation's platform support")
    plat_show.add_argument("operation", help="Operation id (e.g. content.lists.manage)")
    plat_show.set_defaults(func=_cmd_platforms_show)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

