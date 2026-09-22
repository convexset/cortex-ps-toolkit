"""CLI for playbook cache, potential-root checks, compare, and extract."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Optional, Sequence, List

from .cache import DEFAULT_TTL_SECONDS, PlaybookCache, format_manifest_text
from .client import PlaybookApiError, PlaybookClient, insert_failure_items, unwrap_saved_playbook
from .delete import (
    delete_playbook_rows,
    format_delete_text,
    order_playbooks_for_delete,
)
from .compare import (
    compare_potential_roots,
    compare_source_to_downloaded_cluster_subplaybook,
    compare_source_to_downloaded_subplaybook,
    summarize_diff_paths,
    unfiltered_field_policy,
)
from .credentials import load_credentials
from .debugio import DebugSink, slug, utc_stamp
from .extract import (
    build_subplaybook,
    build_subplaybook_cluster,
    refactor_cluster_subplaybook_name,
    refactor_parent_copy_name,
    refactor_subplaybook_name,
    rewrite_parent,
    rewrite_parent_cluster,
    rewrite_parent_combined,
    rewrite_parent_multi,
)
from .fields import FieldPolicy, load_policy_file
from .graph import check_combined_extract, check_multi_extract, check_potential_root
from .inspect import (
    evaluate_expects,
    format_inspect_text,
    inspect_playbook,
    parse_expect_spec,
    resolve_task_ref,
)
from .bindings import id_to_name_map, prepare_playbook_for_yaml_export
from .playbook_update import (
    expand_error_updates_from_matches,
    overwrite_playbook_description,
    overwrite_playbook_task_updates,
)
from .refactor_descriptions import descriptions_for_refactor, embed_sub_playbook_description_on_job
from .task_match import parse_post_task_update_spec, parse_task_name_match
from .keys import JsonDict, get_field, playbook_tasks, start_task_id, task_name, task_type, inner_task
from .validate_batch import load_jobs, merge_job_manifests, validate_jobs
from .context_sharing import (
    TaskContextUpdate,
    apply_playbook_context_updates,
    format_context_state_lines,
    parse_context_update_spec,
    preflight_context_updates,
    read_task_context_state,
    validate_task_context_states,
)
from .error_retry import (
    TaskErrorUpdate,
    apply_playbook_error_updates,
    format_task_state_lines,
    parse_update_spec,
    preflight_error_updates,
    read_task_error_state,
    validate_task_states,
)
from .yaml_codec import dumps_yaml
from .yaml_keys_discover import discover_yaml_keys, load_json_playbook
from .yaml_upload import collect_yaml_paths, format_upload_report, upload_many
from .lists import copy_lists, format_list_copy_report, list_all
from .task_input_search import format_task_input_search_text, search_task_inputs
from .task_output_search import format_task_output_search_text, search_task_outputs
from .task_text_search import (
    format_task_text_search_agent,
    format_task_text_search_text,
    search_task_text,
)
from .condition_branches import (
    analyze_condition_branches_by_ref,
    format_condition_branch_report_agent,
    format_condition_branch_report_text,
)
from .task_show import format_task_show_agent, show_task_by_ref, show_tasks_by_name


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = PACKAGE_ROOT / ".cache"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="playbook_utils",
        description="Load, inspect, and factor XSOAR 6 / XSOAR 8 playbooks via the Core API.",
    )
    parser.add_argument("--credentials", help="JSON file with url, id, key")
    parser.add_argument(
        "--tenant-type",
        "--platform",
        dest="tenant_type",
        choices=["xsoar6", "xsoar8", "xsiam"],
        help="Tenant API family: xsoar6 (/playbook/...), xsoar8 (/xsoar/public/v1/playbook/...), xsiam (/public_api/v1/playbooks/...)",
    )
    parser.add_argument("--insecure", action="store_true", help="Disable TLS certificate verification")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR), help="Playbook cache root")
    parser.add_argument("--cache-ttl", type=float, default=DEFAULT_TTL_SECONDS, help="Cache TTL in seconds (0 = never expire until invalidate)")
    parser.add_argument("--fields-config", help="JSON file overriding ignore/drop field lists")
    parser.add_argument("--debug-dir", help="Directory for machine/human debug artifacts")
    parser.add_argument("--quiet", action="store_true", help="Less human logging")
    parser.add_argument("--print-json", action="store_true", help="Print the command result JSON to stdout")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("cache-status", help="Show cache freshness and counts")
    sub.add_parser("cache-invalidate", help="Delete the on-disk cache for this tenant")
    refresh = sub.add_parser("cache-refresh", help="Download all playbooks into the cache")
    refresh.add_argument("--query", default="", help="Optional playbook search query")

    list_cmd = sub.add_parser("list", help="List cached playbooks (refresh if stale)")
    list_cmd.add_argument("--force", action="store_true")

    get_cmd = sub.add_parser("get", help="Download one playbook by id or name")
    get_cmd.add_argument("playbook", help="Playbook id or name")
    get_cmd.add_argument("--force", action="store_true")

    check = sub.add_parser("check-root", help="(A) Test whether a task is a potential root")
    check.add_argument("--playbook", required=True)
    check.add_argument("--task", required=True, help="Task id (tasks map key)")
    check.add_argument("--force", action="store_true")

    inspect_cmd = sub.add_parser(
        "inspect",
        help="Show task titles, total successors, and potential-root status; optional --check assertions",
    )
    inspect_cmd.add_argument("--playbook", required=True)
    inspect_cmd.add_argument(
        "--task",
        action="append",
        dest="tasks",
        help="Task id to include (repeatable). Default: all tasks",
    )
    inspect_cmd.add_argument(
        "--check",
        action="append",
        dest="checks",
        help="Assertion spec: '7,name=Print Key_In_Main,successors=2,root=yes' (repeatable)",
    )
    inspect_cmd.add_argument("--force", action="store_true")

    search_inputs = sub.add_parser(
        "search-task-inputs",
        help="Find tasks whose inputs contain a substring across sub-playbooks",
    )
    search_inputs.add_argument("--playbook", required=True, help="Root playbook id or name")
    search_inputs.add_argument(
        "--contains",
        required=True,
        help="Case-insensitive substring to search in serialized task inputs",
    )
    search_inputs.add_argument("--force", action="store_true")

    search_tasks = sub.add_parser(
        "search-tasks",
        help="Full-text search across tasks in a playbook tree",
    )
    search_tasks.add_argument("--playbook", required=True, help="Root playbook id or name")
    search_tasks.add_argument(
        "--contains",
        required=True,
        help="Case-insensitive substring to search in serialized task content",
    )
    search_tasks.add_argument(
        "--name-contains",
        help="Optional filter: task name must also contain this substring",
    )
    search_tasks.add_argument(
        "--format",
        choices=("agent", "table"),
        default="agent",
        help="Output style: agent (compact summaries, default) or table",
    )
    search_tasks.add_argument("--force", action="store_true")

    search_outputs = sub.add_parser(
        "search-task-outputs",
        help="Find tasks whose outputs contain a substring across sub-playbooks",
    )
    search_outputs.add_argument("--playbook", required=True, help="Root playbook id or name")
    search_outputs.add_argument(
        "--contains",
        required=True,
        help="Case-insensitive substring to search in serialized task outputs",
    )
    search_outputs.add_argument(
        "--script",
        help="Only include tasks bound to this script/command (e.g. setIssue, HttpV2)",
    )
    search_outputs.add_argument("--force", action="store_true")

    trace_branches = sub.add_parser(
        "trace-branches",
        help="Analyze condition branches and trace upstream variable assignments",
    )
    trace_branches.add_argument("--playbook", required=True, help="Root playbook id or name")
    trace_branches.add_argument(
        "--task",
        required=True,
        help="Condition task id or unique task name (searched in root + sub-playbooks)",
    )
    trace_branches.add_argument(
        "--format",
        choices=("agent", "table"),
        default="agent",
        help="Output style: agent (branch drivers + task summaries, default) or table",
    )
    trace_branches.add_argument("--force", action="store_true")

    show_task = sub.add_parser(
        "show-task",
        help="Show compact task summary by id/name (root + sub-playbooks)",
    )
    show_task.add_argument("--playbook", required=True, help="Root playbook id or name")
    show_task.add_argument("--task", help="Task id or unique task name")
    show_task.add_argument(
        "--name-contains",
        help="Show all tasks whose name contains this substring",
    )
    show_task.add_argument("--force", action="store_true")

    compare = sub.add_parser("compare", help="(B) Compare two potential-root subgraphs")
    compare.add_argument("--playbook-a", required=True)
    compare.add_argument("--task-a", required=True)
    compare.add_argument("--playbook-b", required=True)
    compare.add_argument("--task-b", required=True)
    compare.add_argument("--skip-start-a", action="store_true")
    compare.add_argument("--skip-start-b", action="store_true")
    compare.add_argument("--force", action="store_true")

    extract = sub.add_parser("extract", help="Factor a task and descendants into a sub-playbook")
    extract.add_argument("--playbook", required=True)
    extract.add_argument("--task", required=True, help="Task id (tasks map key) or unique task name")
    extract.add_argument("--sub-playbook-name")
    extract.add_argument("--parent-copy-name")
    extract.add_argument(
        "--damp-run",
        action="store_true",
        help="Upload and compare, then delete the created playbooks and report the outcome",
    )
    extract.add_argument("--require-match", action="store_true", help="Exit 2 if downloaded sub-playbook does not match")
    extract.add_argument("--upload-parent-on-mismatch", action="store_true")
    extract.add_argument("--skip-parent", action="store_true", help="Only create/upload the sub-playbook")
    extract.add_argument(
        "--upload-only",
        action="store_true",
        help="Upload sub-playbook and parent copy only; skip re-download and compare (use validate-jobs later)",
    )
    extract.add_argument("--force", action="store_true")
    extract.add_argument("--padding", type=float, default=400.0)

    extract_multi = sub.add_parser(
        "extract-multi",
        help="Factor several tasks from one playbook into sub-playbooks and one parent copy",
    )
    extract_multi.add_argument("--playbook", required=True)
    extract_multi.add_argument(
        "--task",
        action="append",
        dest="tasks",
        help="Potential-root task id or unique task name (repeatable)",
    )
    extract_multi.add_argument(
        "--cluster",
        action="append",
        dest="clusters",
        metavar="START:END",
        help="Cluster extract from START to END task id or name (repeatable)",
    )
    extract_multi.add_argument("--parent-copy-name")
    extract_multi.add_argument("--damp-run", action="store_true")
    extract_multi.add_argument("--require-match", action="store_true")
    extract_multi.add_argument("--upload-parent-on-mismatch", action="store_true")
    extract_multi.add_argument("--upload-only", action="store_true")
    extract_multi.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="Replace sub-playbooks and parent copy when names already exist on the tenant",
    )
    extract_multi.add_argument("--force", action="store_true")
    extract_multi.add_argument("--padding", type=float, default=400.0)
    extract_multi.add_argument(
        "--parallel",
        action="store_true",
        help="Experimental: parallel sub upload/compare/post-steps (default is sequential)",
    )
    extract_multi.add_argument(
        "--compare-after-parent",
        action="store_true",
        help="Upload subs, refresh, upload parent, refresh again, then compare subs (5-phase refactor)",
    )
    extract_multi.add_argument(
        "--parallel-workers",
        type=int,
        default=None,
        metavar="N",
        help="Max worker threads for --parallel (default 5, capped by job count)",
    )
    extract_multi.add_argument(
        "--post-task-update",
        action="append",
        dest="post_task_updates",
        default=[],
        metavar="MATCH|actions",
        help=(
            "After refactor compare/upload succeeds: refresh cache, then apply update actions "
            "in place on generated sub-playbooks for regular script tasks whose title matches "
            "MATCH (e.g. 'contains:HttpV2:i|retry=20x30,stop-on-error')"
        ),
    )

    validate = sub.add_parser(
        "validate-jobs",
        help="After a batch upload: refresh cache once, compare jobs, delete failures by default",
    )
    validate.add_argument(
        "--jobs",
        action="append",
        required=True,
        help="JSON file with upload job record(s); repeat to merge multiple manifests",
    )
    validate.add_argument(
        "--keep-failures",
        action="store_true",
        help="Keep uploaded playbooks even when compare fails",
    )
    validate.add_argument(
        "--no-refresh-before",
        action="store_true",
        help="Skip the initial cache refresh (cache must already include uploaded playbooks)",
    )
    validate.add_argument(
        "--no-refresh-after-deletes",
        action="store_true",
        help="Skip cache refresh after deleting failed uploads",
    )

    delete_cmd = sub.add_parser("delete", help="Delete playbooks by id/name or name prefix")
    delete_cmd.add_argument(
        "--playbook",
        action="append",
        dest="playbooks",
        help="Playbook id or unique name (repeatable)",
    )
    delete_cmd.add_argument(
        "--name-prefix",
        help="Case-sensitive name prefix (e.g. '[REFACTOR'). Parents are deleted before sub-playbooks.",
    )
    delete_cmd.add_argument("--force", action="store_true", help="Refresh the cache before matching")

    discover = sub.add_parser(
        "discover-yaml-keys",
        help="From a tenant YAML export, find the key spellings /playbook/save/yaml accepts",
    )
    discover.add_argument("--yaml", required=True, help="Exported playbook YAML")
    discover.add_argument("--json", help="API JSON for the same playbook (cached get/search)")
    discover.add_argument("--playbook", help="Load API JSON from the tenant cache by id or name")
    discover.add_argument(
        "--task",
        action="append",
        dest="tasks",
        help="Limit value search to these task ids (repeatable). Default: all tasks",
    )
    discover.add_argument("--force", action="store_true")

    for cmd_name in ("update-playbook-tasks", "update-error-retry"):
        update_tasks = sub.add_parser(
            cmd_name,
            help=(
                "Overwrite a playbook in place: On Error retry / error-handling on regular "
                "script tasks, and context sharing on sub-playbook call tasks"
            ),
        )
        update_tasks.add_argument(
            "--playbook",
            help="Playbook id or name to overwrite in place (omit when using --name-prefix)",
        )
        update_tasks.add_argument(
            "--update",
            action="append",
            dest="updates",
            default=[],
            metavar="TASK:actions",
            help=(
                "Retry/error-handling update for a regular script task (repeatable), e.g. "
                "'8:retry=15x45' or '1:clear-retry,stop-on-error'"
            ),
        )
        update_tasks.add_argument(
            "--context-update",
            action="append",
            dest="context_updates",
            default=[],
            metavar="TASK:sharing",
            help=(
                "Context-sharing update for a sub-playbook call task (repeatable), e.g. "
                "'4:global' or '4:subplaybook'"
            ),
        )
        update_tasks.add_argument(
            "--validate-task",
            action="append",
            dest="validate_tasks",
            help="Additional task id to include in before/after validation (repeatable)",
        )
        update_tasks.add_argument(
            "--dry-run",
            action="store_true",
            help="Build upload YAML and validation expectations without calling save/yaml",
        )
        update_tasks.add_argument(
            "--force", action="store_true", help="Refresh cache before loading the playbook"
        )
        update_tasks.add_argument(
            "--name-prefix",
            help="Apply updates to every playbook whose name starts with this prefix (case-sensitive)",
        )
        update_tasks.add_argument(
            "--match-task-name",
            action="append",
            dest="match_task_names",
            default=[],
            metavar="SPEC",
            help=(
                "Match regular script tasks by title: contains:PATTERN, equals:PATTERN, "
                "optional trailing :i for case-insensitive; bare PATTERN means contains"
            ),
        )
        update_tasks.add_argument(
            "--match-update",
            help="Actions applied to every task matched by --match-task-name (e.g. retry=20x30,stop-on-error)",
        )

    upload_playbooks = sub.add_parser(
        "upload-playbooks",
        help="Upload playbook YAML exports (XSOAR 6/8 save/yaml; XSIAM playbooks/insert ZIP)",
    )
    upload_playbooks.add_argument(
        "paths",
        nargs="+",
        help="Playbook .yml/.yaml file(s) and/or directories",
    )
    upload_playbooks.add_argument(
        "--recursive",
        action="store_true",
        help="When a path is a directory, include nested .yml/.yaml files",
    )

    upload_scripts = sub.add_parser(
        "upload-scripts",
        help="Upload script YAML exports (XSOAR 6 import; XSOAR 8 automation JSON; XSIAM scripts/insert ZIP)",
    )
    upload_scripts.add_argument(
        "paths",
        nargs="+",
        help="Script .yml/.yaml file(s) and/or directories",
    )
    upload_scripts.add_argument(
        "--recursive",
        action="store_true",
        help="When a path is a directory, include nested .yml/.yaml files",
    )

    list_lists = sub.add_parser(
        "list-lists",
        help="List XSOAR 8 / XSIAM lists (GET /xsoar/public/v1/lists)",
    )
    list_lists.add_argument(
        "--name-contains",
        help="Case-sensitive substring filter on list name/id",
    )

    copy_list = sub.add_parser(
        "copy-list",
        help="Copy list(s) between tenants (XSOAR 8 / XSIAM /xsoar/public/v1/lists/save)",
    )
    copy_list.add_argument(
        "--from-credentials",
        required=True,
        help="Source tenant credentials JSON",
    )
    copy_list.add_argument(
        "--to-credentials",
        required=True,
        help="Destination tenant credentials JSON",
    )
    copy_list.add_argument(
        "--from-tenant-type",
        choices=["xsoar8", "xsiam"],
        help="Override source tenant type (default: detect from credentials file)",
    )
    copy_list.add_argument(
        "--to-tenant-type",
        choices=["xsoar8", "xsiam"],
        help="Override destination tenant type (default: detect from credentials file)",
    )
    copy_list.add_argument(
        "names",
        nargs="+",
        help="List name(s) or id(s) on the source tenant",
    )
    copy_list.add_argument(
        "--target-name",
        help="Rename on destination (single-list copy only)",
    )
    copy_list.add_argument(
        "--target-prefix",
        default="",
        help="Prefix destination list names when copying multiple lists",
    )
    copy_list.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Fail if the destination list already exists",
    )
    copy_list.add_argument(
        "--commit-message",
        default="Copied via playbook-utils",
        help="Commit message sent to lists/save",
    )
    return parser


def _sink_for(args: argparse.Namespace, label: str) -> DebugSink:
    debug_dir = args.debug_dir
    if debug_dir is None and args.command in {
        "check-root",
        "compare",
        "extract",
        "extract-multi",
        "get",
        "inspect",
        "search-task-inputs",
        "search-tasks",
        "search-task-outputs",
        "trace-branches",
        "show-task",
        "cache-refresh",
        "list",
        "delete",
        "discover-yaml-keys",
        "validate-jobs",
        "update-error-retry",
        "update-playbook-tasks",
        "upload-playbooks",
        "upload-scripts",
        "list-lists",
        "copy-list",
    }:
        debug_dir = str(Path.cwd() / ".debug" / f"{utc_stamp()}-{slug(label)}")
    return DebugSink(Path(debug_dir) if debug_dir else None, verbose=not args.quiet)


def _runtime(args: argparse.Namespace):
    if not args.credentials:
        raise SystemExit("error: --credentials is required")
    creds = load_credentials(args.credentials, platform=args.tenant_type, verify_ssl=not args.insecure)
    client = PlaybookClient(creds)
    cache = PlaybookCache(creds, client, Path(args.cache_dir), ttl_seconds=args.cache_ttl)
    policy = load_policy_file(args.fields_config)
    return creds, client, cache, policy


def _emit(sink: DebugSink, args: argparse.Namespace, payload: Any, *, text: Optional[str] = None) -> None:
    sink.write_json("00-result.json", payload)
    if text:
        sink.write_text("00-result.txt", text)
        sink.log(text)
    elif not args.quiet:
        sink.log(json.dumps(payload, indent=2, default=str))
    if args.print_json:
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")


def cmd_cache_status(args: argparse.Namespace) -> int:
    _creds, _client, cache, _policy = _runtime(args)
    sink = _sink_for(args, "cache-status")
    payload = cache.status()
    _emit(sink, args, payload)
    return 0


def cmd_cache_invalidate(args: argparse.Namespace) -> int:
    _creds, _client, cache, _policy = _runtime(args)
    sink = _sink_for(args, "cache-invalidate")
    cache.invalidate()
    _emit(sink, args, {"invalidated": True, "cache_dir": str(cache.root)})
    return 0


def cmd_cache_refresh(args: argparse.Namespace) -> int:
    creds, _client, cache, _policy = _runtime(args)
    sink = _sink_for(args, "cache-refresh")
    playbooks = cache.refresh(query=args.query or None)
    manifest = cache.write_manifest()
    text = format_manifest_text(manifest)
    sink.write_json("manifest.json", manifest)
    sink.write_text("manifest.txt", text)
    _emit(
        sink,
        args,
        manifest,
        text=text + f"\n\nWrote {len(playbooks)} playbook JSON files under {cache.playbooks_dir}",
    )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    _creds, _client, cache, _policy = _runtime(args)
    sink = _sink_for(args, "list")
    cache.list_summaries(force=args.force)
    manifest = cache.write_manifest()
    text = format_manifest_text(manifest)
    sink.write_json("manifest.json", manifest)
    sink.write_text("manifest.txt", text)
    _emit(sink, args, manifest, text=text)
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    _creds, _client, cache, _policy = _runtime(args)
    sink = _sink_for(args, args.playbook)
    playbook = cache.resolve(args.playbook, force=args.force)
    sink.write_json("01-playbook.json", playbook)
    tasks = playbook_tasks(playbook)
    summary = {
        "id": playbook.get("id"),
        "name": playbook.get("name"),
        "startTaskId": start_task_id(playbook),
        "task_count": len(tasks),
        "tasks": [
            {"id": tid, "type": task_type(node), "name": task_name(node)}
            for tid, node in tasks.items()
        ],
    }
    _emit(sink, args, summary, text=f"{playbook.get('name')} ({playbook.get('id')}): {len(tasks)} tasks")
    return 0


def cmd_check_root(args: argparse.Namespace) -> int:
    _creds, _client, cache, _policy = _runtime(args)
    sink = _sink_for(args, f"{args.playbook}-{args.task}")
    playbook = cache.resolve(args.playbook, force=args.force)
    sink.write_json("01-playbook.json", playbook)
    result = check_potential_root(playbook, args.task)
    sink.write_json("02-potential-root.json", result.to_dict())
    lines = [
        f"playbook: {playbook.get('name')} ({playbook.get('id')})",
        f"task: {args.task}",
        f"potential_root: {result.ok}",
    ]
    if result.reasons:
        lines.append("reasons:")
        lines.extend(f"  - {reason}" for reason in result.reasons)
    lines.append(f"descendants: {len(result.descendant_ids)}")
    lines.append(" ".join(result.descendant_ids))
    _emit(sink, args, result.to_dict(), text="\n".join(lines))
    return 0 if result.ok else 2


def cmd_trace_branches(args: argparse.Namespace) -> int:
    _creds, _client, cache, _policy = _runtime(args)
    sink = _sink_for(args, f"trace-branches-{args.playbook}-{args.task}")
    root_playbook = cache.resolve(args.playbook, force=args.force)
    report = analyze_condition_branches_by_ref(root_playbook, cache, args.task)
    text = (
        format_condition_branch_report_agent(report)
        if args.format == "agent"
        else format_condition_branch_report_text(report)
    )
    sink.write_json("01-playbook.json", {"id": root_playbook.get("id"), "name": root_playbook.get("name")})
    sink.write_json("02-trace-branches.json", report.to_dict())
    sink.write_text("02-trace-branches.txt", text)
    _emit(sink, args, report.to_dict(), text=text)
    return 0


def cmd_search_tasks(args: argparse.Namespace) -> int:
    _creds, _client, cache, _policy = _runtime(args)
    sink = _sink_for(args, f"search-tasks-{args.playbook}")
    playbook = cache.resolve(args.playbook, force=args.force)
    result = search_task_text(
        playbook,
        cache,
        args.contains,
        name_contains=args.name_contains,
    )
    text = (
        format_task_text_search_agent(result)
        if args.format == "agent"
        else format_task_text_search_text(result)
    )
    sink.write_json("01-playbook.json", {"id": playbook.get("id"), "name": playbook.get("name")})
    sink.write_json("02-search-tasks.json", result.to_dict())
    sink.write_text("02-search-tasks.txt", text)
    _emit(sink, args, result.to_dict(), text=text)
    return 0 if result.matches else 1


def cmd_show_task(args: argparse.Namespace) -> int:
    if not args.task and not args.name_contains:
        raise ValueError("show-task requires --task or --name-contains")
    _creds, _client, cache, _policy = _runtime(args)
    label = args.task or f"name-{args.name_contains}"
    sink = _sink_for(args, f"show-task-{args.playbook}-{label}")
    playbook = cache.resolve(args.playbook, force=args.force)
    if args.task:
        result = show_task_by_ref(playbook, cache, args.task)
    else:
        result = show_tasks_by_name(playbook, cache, args.name_contains)
    text = format_task_show_agent(result)
    sink.write_json("01-playbook.json", {"id": playbook.get("id"), "name": playbook.get("name")})
    sink.write_json("02-show-task.json", result.to_dict())
    sink.write_text("02-show-task.txt", text)
    _emit(sink, args, result.to_dict(), text=text)
    return 0 if result.tasks else 1


def cmd_search_task_outputs(args: argparse.Namespace) -> int:
    _creds, _client, cache, _policy = _runtime(args)
    sink = _sink_for(args, f"search-task-outputs-{args.playbook}")
    playbook = cache.resolve(args.playbook, force=args.force)
    result = search_task_outputs(
        playbook,
        cache,
        args.contains,
        script_filter=args.script,
    )
    text = format_task_output_search_text(result)
    sink.write_json("01-playbook.json", {"id": playbook.get("id"), "name": playbook.get("name")})
    sink.write_json("02-search-task-outputs.json", result.to_dict())
    sink.write_text("02-search-task-outputs.txt", text)
    _emit(sink, args, result.to_dict(), text=text)
    return 0 if result.matches else 1


def cmd_search_task_inputs(args: argparse.Namespace) -> int:
    _creds, _client, cache, _policy = _runtime(args)
    sink = _sink_for(args, f"search-task-inputs-{args.playbook}")
    playbook = cache.resolve(args.playbook, force=args.force)
    result = search_task_inputs(playbook, cache, args.contains)
    text = format_task_input_search_text(result)
    sink.write_json("01-playbook.json", {"id": playbook.get("id"), "name": playbook.get("name")})
    sink.write_json("02-search-task-inputs.json", result.to_dict())
    sink.write_text("02-search-task-inputs.txt", text)
    _emit(sink, args, result.to_dict(), text=text)
    return 0 if result.matches else 1


def cmd_inspect(args: argparse.Namespace) -> int:
    _creds, _client, cache, _policy = _runtime(args)
    sink = _sink_for(args, f"inspect-{args.playbook}")
    playbook = cache.resolve(args.playbook, force=args.force)
    sink.write_json("01-playbook.json", playbook)

    specs = [parse_expect_spec(item) for item in (args.checks or [])]
    selected = list(args.tasks or [])
    for spec in specs:
        if spec.task_id not in selected:
            selected.append(spec.task_id)
    reports = inspect_playbook(playbook, selected or None)
    expects = evaluate_expects(playbook, specs) if specs else []
    text = format_inspect_text(playbook, reports, expects or None)
    payload: JsonDict = {
        "id": playbook.get("id"),
        "name": playbook.get("name"),
        "startTaskId": start_task_id(playbook),
        "task_count": len(playbook_tasks(playbook)),
        "tasks": [report.to_dict() for report in reports],
        "checks": [item.to_dict() for item in expects],
        "ok": all(item.ok for item in expects) if expects else True,
    }
    sink.write_json("02-inspect.json", payload)
    sink.write_text("02-inspect.txt", text)
    _emit(sink, args, payload, text=text)
    if any(not item.ok for item in expects):
        return 2
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    _creds, _client, cache, policy = _runtime(args)
    sink = _sink_for(args, f"compare-{args.task_a}-{args.task_b}")
    left = cache.resolve(args.playbook_a, force=args.force)
    right = cache.resolve(args.playbook_b, force=args.force)
    sink.write_json("01-playbook-a.json", left)
    sink.write_json("02-playbook-b.json", right)
    compared = compare_potential_roots(
        left,
        args.task_a,
        right,
        args.task_b,
        policy=policy,
        skip_start_left=True if args.skip_start_a else None,
        skip_start_right=True if args.skip_start_b else None,
    )
    sink.write_json("03-canonical-left.json", compared.left.to_dict())
    sink.write_json("04-canonical-right.json", compared.right.to_dict())
    sink.write_json("05-compare.json", compared.to_dict())
    text = compared.human_summary()
    sink.write_text("05-compare.txt", text)
    _emit(sink, args, {"equal": compared.equal, "diff_count": len(compared.diffs), **compared.to_dict()}, text=text)
    return 0 if compared.equal else 2


def _damp_run_cleanup(args: argparse.Namespace, client: PlaybookClient, cache: PlaybookCache, sink: DebugSink, result: JsonDict) -> Optional[int]:
    """Delete playbooks created by this extract. Returns 1 if a delete failed."""
    info = result.get("damp_run")
    if not isinstance(info, dict):
        info = {"enabled": bool(getattr(args, "damp_run", False))}
        result["damp_run"] = info
    if not args.damp_run:
        return None
    created: list[JsonDict] = []
    parent_info = result.get("parent") or {}
    parent_saved = None
    upload = parent_info.get("upload")
    if isinstance(upload, dict):
        parent_saved = unwrap_saved_playbook(upload)
    if parent_saved or parent_info.get("upload"):
        created.append(
            {
                "id": str((parent_saved or {}).get("id") or parent_info.get("id") or ""),
                "name": str(
                    (parent_saved or {}).get("name")
                    or parent_info.get("name")
                    or result.get("parent_copy_name")
                    or ""
                ),
            }
        )
    sub = result.get("uploaded_subplaybook")
    if isinstance(sub, dict):
        created.append(
            {
                "id": str(sub.get("id") or ""),
                "name": str(sub.get("name") or result.get("subplaybook_name") or ""),
            }
        )
    created = [row for row in created if row.get("id") or row.get("name")]
    ordered = order_playbooks_for_delete(created)
    outcomes = delete_playbook_rows(ordered, delete_fn=client.delete_playbook, log=sink.log)
    cache.on_delete()
    info["deleted"] = sum(1 for row in outcomes if row.get("ok"))
    info["failed"] = sum(1 for row in outcomes if not row.get("ok"))
    info["outcomes"] = outcomes
    sink.write_json("11-damp-run.json", info)
    sink.log(format_delete_text(outcomes))
    if any(not row.get("ok") for row in outcomes):
        return 1
    return None


def _dedupe_error_updates(updates: list) -> list:
    by_id: dict[str, object] = {}
    for update in updates:
        by_id[update.task_id] = update
    return list(by_id.values())


def _apply_refactor_descriptions(
    *,
    client: PlaybookClient,
    cache: PlaybookCache,
    policy: FieldPolicy,
    sink: DebugSink,
    source: JsonDict,
    parent: JsonDict,
    post_result: Optional[JsonDict],
    post_specs: Sequence[str],
    skip_sub_uploads: bool = False,
) -> tuple[JsonDict, JsonDict]:
    """Apply generated descriptions to subs (overwrite) and the parent copy (in-memory)."""
    refactor = parent.get("_refactor") or {}
    payload = descriptions_for_refactor(
        source=source,
        refactor=refactor,
        post_result=post_result,
        post_specs=post_specs,
    )
    sink.write_json("12-refactor-descriptions.json", payload)
    sink.write_text("12-parent-description.txt", str(payload.get("parent_description") or ""))
    sink.write_text("12-refactor-metrics.txt", str(payload.get("metrics_log") or ""))
    sink.log("Refactor metrics written to 12-refactor-metrics.txt")

    sub_outcomes: list[JsonDict] = []
    sub_items = sorted((payload.get("sub_descriptions") or {}).items())
    for index, (sub_name, description) in enumerate(sub_items, 1):
        sink.write_text(f"12-sub-description-{index:02d}.txt", description)
    if skip_sub_uploads:
        sink.log("Sub-playbook descriptions were set on initial upload; skipping sub description overwrites")
        for sub_name, _description in sub_items:
            sub_outcomes.append(
                {
                    "playbook_name": sub_name,
                    "ok": True,
                    "skipped": True,
                    "reason": "embedded_at_upload",
                }
            )
    else:
        for index, (sub_name, description) in enumerate(sub_items, 1):
            try:
                sub_playbook = cache.resolve(sub_name, force=False)
            except Exception as exc:
                sink.log(f"Could not resolve sub-playbook {sub_name!r} for description overwrite: {exc}")
                sub_outcomes.append(
                    {
                        "playbook_name": sub_name,
                        "ok": False,
                        "error": str(exc),
                    }
                )
                continue
            outcome = overwrite_playbook_description(
                client=client,
                cache=cache,
                policy=policy,
                playbook=sub_playbook,
                description=description,
                sink=sink,
            )
            sink.write_json(f"12-sub-description-upload-{index:02d}.json", outcome)
            sub_outcomes.append(outcome)

    parent = copy.deepcopy(parent)
    parent["description"] = str(payload.get("parent_description") or "")
    parent.pop("comment", None)
    result = {
        "ok": all(row.get("ok") for row in sub_outcomes) if sub_outcomes else True,
        "sub_outcomes": sub_outcomes,
        "extraction_count": payload.get("extraction_count"),
        "httpv2_task_count": payload.get("httpv2_task_count"),
    }
    return parent, result


def _run_post_task_updates(
    *,
    client: PlaybookClient,
    cache: PlaybookCache,
    policy: FieldPolicy,
    playbook_names: Sequence[str],
    post_specs: Sequence[str],
    sink: DebugSink,
) -> JsonDict:
    rules = [parse_post_task_update_spec(spec) for spec in post_specs]
    sink.log("Refreshing cache before post-task updates")
    cache.refresh()
    outcomes: list[JsonDict] = []
    for index, name in enumerate(playbook_names, 1):
        playbook = cache.resolve(name, force=False)
        error_updates: list = []
        rejected: list[JsonDict] = []
        for match, actions in rules:
            expanded, rule_rejected = expand_error_updates_from_matches(playbook, [match], actions)
            error_updates.extend(expanded)
            rejected.extend(rule_rejected)
        error_updates = _dedupe_error_updates(error_updates)
        sink.write_json(f"11-post-update-source-{index:02d}.json", playbook)
        if not error_updates:
            sink.log(f"Post-update skip {name!r}: no matching regular script tasks")
            outcomes.append(
                {
                    "playbook_name": name,
                    "ok": True,
                    "skipped": True,
                    "reason": "no matching tasks",
                    "error_rejected": rejected,
                }
            )
            continue
        outcome = overwrite_playbook_task_updates(
            client=client,
            cache=cache,
            policy=policy,
            playbook=playbook,
            error_updates=error_updates,
            context_updates=[],
            sink=sink,
        )
        outcome["error_rejected"] = list(outcome.get("error_rejected") or []) + rejected
        if rejected:
            outcome["ok"] = False
        sink.write_json(f"11-post-update-outcome-{index:02d}.json", outcome)
        outcomes.append(outcome)
    return {
        "playbook_count": len(playbook_names),
        "ok": all(row.get("ok") for row in outcomes),
        "outcomes": outcomes,
    }


def _resolve_update_playbook_targets(args: argparse.Namespace, cache: PlaybookCache) -> list[JsonDict]:
    if args.name_prefix:
        if args.force:
            cache.refresh()
        return cache.find_by_name_prefix(args.name_prefix)
    return [cache.resolve(args.playbook, force=args.force)]


def _collect_error_updates_for_playbook(
    playbook: JsonDict,
    *,
    explicit_specs: Sequence[str],
    match_specs: Sequence[str],
    match_actions: Optional[str],
) -> tuple[list, list[JsonDict]]:
    error_updates_requested = [parse_update_spec(spec) for spec in explicit_specs]
    error_updates, error_rejected = preflight_error_updates(playbook, error_updates_requested)
    if match_specs:
        if not match_actions:
            raise SystemExit("error: --match-task-name requires --match-update ACTIONS")
        matches = [parse_task_name_match(spec) for spec in match_specs]
        matched, match_rejected = expand_error_updates_from_matches(playbook, matches, match_actions)
        error_updates = _dedupe_error_updates(list(error_updates) + matched)
        error_rejected = list(error_rejected) + match_rejected
    return error_updates, error_rejected


def _finish_extract(
    args: argparse.Namespace,
    client: PlaybookClient,
    cache: PlaybookCache,
    sink: DebugSink,
    result: JsonDict,
    *,
    exit_code: int,
    text: Optional[str] = None,
) -> int:
    damp = _damp_run_cleanup(args, client, cache, sink, result)
    _emit(sink, args, result, text=text)
    return 1 if damp == 1 else exit_code


def cmd_extract(args: argparse.Namespace) -> int:
    creds, client, cache, policy = _runtime(args)
    sink = _sink_for(args, f"extract-{args.playbook}-{args.task}")
    playbook = cache.resolve(args.playbook, force=args.force)
    sink.write_json("01-source-playbook.json", playbook)
    sink.write_json("00-field-policy.json", policy.to_dict())

    task_id = resolve_task_ref(playbook, args.task)
    check = check_potential_root(playbook, task_id)
    sink.write_json("02-potential-root.json", check.to_dict())
    if not check.ok:
        _emit(sink, args, check.to_dict(), text="Not a potential root:\n" + "\n".join(check.reasons))
        return 2

    task_label = task_name(playbook_tasks(playbook)[task_id]) or task_id
    parent_name = str(playbook.get("name") or "playbook")
    sub_name = args.sub_playbook_name or refactor_subplaybook_name(parent_name, task_label, task_id=task_id)
    parent_copy_name = args.parent_copy_name or refactor_parent_copy_name(parent_name)

    sub = build_subplaybook(playbook, task_id, name=sub_name, root_check=check)
    script_names, playbook_names = _load_script_and_playbook_names(client, playbook, cache, sink)
    bind_by_id = creds.platform.value == "xsiam"
    sub, sub_prep = prepare_playbook_for_yaml_export(sub, cache)
    if sub_prep.get("unresolved_bindings"):
        sink.write_json("03-subplaybook-bindings.json", sub_prep)
        sink.log(
            f"Warning: {len(sub_prep['unresolved_bindings'])} unresolved playbook binding(s) in sub-playbook"
        )
    embed_sub_playbook_description_on_job(
        source=playbook,
        job={"subplaybook_name": sub_name, "sub": sub},
        post_specs=list(getattr(args, "post_task_updates", None) or []),
    )
    sub_yaml = dumps_yaml(
        sub,
        policy=policy,
        script_names=script_names,
        playbook_names=playbook_names,
        bind_subplaybooks_by_id=bind_by_id,
    )
    sink.write_json("03-subplaybook-built.json", sub)
    sink.write_text("03-subplaybook-built.yaml", sub_yaml)

    result: JsonDict = {
        "platform": creds.platform.value,
        "phase": "upload" if args.upload_only else "full",
        "source_playbook": {"id": playbook.get("id"), "name": playbook.get("name")},
        "task_id": task_id,
        "potential_root": check.to_dict(),
        "subplaybook_name": sub_name,
        "parent_copy_name": parent_copy_name,
        "damp_run": {"enabled": bool(args.damp_run)},
        "uploaded_subplaybook": None,
        "compare": None,
        "parent": None,
    }

    downloaded = None
    upload_response = None
    sink.log(f"Uploading sub-playbook {sub_name!r}")
    upload_response = client.save_yaml(sub_yaml, filename=f"{slug(sub_name)}.yml")
    cache.on_upload()
    sink.write_json("04-subplaybook-upload.json", upload_response)
    failures = insert_failure_items(upload_response)
    already_exists = any("already exists" in str(item.get("error") or "").lower() for item in failures)
    if failures and not already_exists:
        result["upload_error"] = failures
        text = "Sub-playbook upload failed:\n" + "\n".join(
            f"  {item.get('id')}: {item.get('error')}" for item in failures
        )
        return _finish_extract(args, client, cache, sink, result, exit_code=1, text=text)
    saved = unwrap_saved_playbook(upload_response) or {}
    saved_id = str(saved.get("id") or "")
    result["uploaded_subplaybook"] = {
        "id": saved_id or None,
        "name": sub_name,
        "upload_response_keys": list(upload_response.keys()) if upload_response else [],
        "already_exists": already_exists,
    }

    if args.upload_only:
        sink.log("Upload-only: skipping re-download and compare")
    else:
        try:
            if already_exists:
                sink.log(f"Sub-playbook already exists; reloading {sub_name!r} from search/cache")
            elif creds.platform.value == "xsiam":
                sink.log("Refreshing XSIAM search cache for JSON vs JSON compare")
            downloaded = cache.redownload_after_save(playbook_id=saved_id or None, name=sub_name)
        except Exception as exc:
            sink.log(f"Failed to re-download sub-playbook: {exc}")
            result["download_error"] = str(exc)
        if downloaded is not None:
            sink.write_json("05-subplaybook-downloaded.json", downloaded)
            result["uploaded_subplaybook"] = {
                "id": downloaded.get("id"),
                "name": downloaded.get("name"),
                "upload_response_keys": list(upload_response.keys()) if upload_response else [],
            }

    compared = None
    if downloaded is not None and not args.upload_only:
        compared = compare_source_to_downloaded_subplaybook(
            playbook,
            task_id,
            downloaded,
            policy=policy,
            allowed_task_ids=set(check.descendant_ids),
        )
        sink.write_json("06-canonical-source.json", compared.left.to_dict())
        sink.write_json("07-canonical-downloaded.json", compared.right.to_dict())
        sink.write_json("08-compare.json", compared.to_dict())
        sink.write_text("08-compare.txt", compared.human_summary())
        result["compare"] = {
            "equal": compared.equal,
            "diff_count": len(compared.diffs),
            "diff_counts": summarize_diff_paths(compared.diffs),
            "diffs": [d.to_dict() for d in compared.diffs],
            "left_root": compared.left_root,
            "right_root": compared.right_root,
            "warnings": compared.left.warnings + compared.right.warnings,
        }
        sink.log("Policy compare (ignored keys applied):\n" + compared.human_summary())

        unfiltered = compare_source_to_downloaded_subplaybook(
            playbook,
            task_id,
            downloaded,
            policy=unfiltered_field_policy(),
            allowed_task_ids=set(check.descendant_ids),
        )
        sink.write_json("08b-compare-all-fields.json", unfiltered.to_dict())
        sink.write_text("08b-compare-all-fields.txt", unfiltered.human_summary())
        result["compare_all_fields"] = {
            "equal": unfiltered.equal,
            "diff_count": len(unfiltered.diffs),
            "diff_counts": summarize_diff_paths(unfiltered.diffs),
            "diffs": [d.to_dict() for d in unfiltered.diffs],
            "left_root": unfiltered.left_root,
            "right_root": unfiltered.right_root,
            "warnings": unfiltered.left.warnings + unfiltered.right.warnings,
        }
        sink.log("All-fields compare (nothing ignored):\n" + unfiltered.human_summary())

    mismatch = bool(not args.upload_only and (compared is None or not compared.equal))
    if mismatch and args.require_match:
        return _finish_extract(
            args, client, cache, sink, result, exit_code=2, text="Sub-playbook round-trip did not match (require-match)."
        )

    if args.skip_parent:
        return _finish_extract(
            args,
            client,
            cache,
            sink,
            result,
            exit_code=2 if mismatch else 0,
            text="Skipped parent rewrite.",
        )

    sub_playbook_id: Optional[str] = None
    if bind_by_id:
        if downloaded is None:
            try:
                downloaded = cache.resolve(sub_name, force=True)
            except Exception as exc:
                sink.log(f"Could not resolve sub-playbook id for parent binding: {exc}")
        sub_playbook_id = str((downloaded or {}).get("id") or saved_id or "") or None

    parent = rewrite_parent(
        playbook,
        task_id,
        subplaybook_name=str((downloaded or sub).get("name") or sub_name),
        subplaybook_id=sub_playbook_id,
        copy_name=parent_copy_name,
        padding=args.padding,
        root_check=check,
    )
    parent, parent_prep = prepare_playbook_for_yaml_export(parent, cache)
    if parent_prep.get("unresolved_bindings"):
        sink.write_json("09-parent-bindings.json", parent_prep)
        sink.log(
            f"Warning: {len(parent_prep['unresolved_bindings'])} unresolved playbook binding(s) in parent copy"
        )
    sink.write_json("09-parent-rewritten.json", parent)
    result["parent"] = parent.get("_refactor")
    result["parent"]["name"] = parent.get("name")
    result["parent"]["id"] = parent.get("id")

    should_upload_parent = args.upload_only or not mismatch or args.upload_parent_on_mismatch
    if not args.upload_only and not mismatch and should_upload_parent:
        sink.log("Applying refactor descriptions to sub-playbook and parent copy")
        parent, description_result = _apply_refactor_descriptions(
            client=client,
            cache=cache,
            policy=policy,
            sink=sink,
            source=playbook,
            parent=parent,
            post_result=None,
            post_specs=[],
            skip_sub_uploads=True,
        )
        result["refactor_descriptions"] = description_result
        parent, parent_prep = prepare_playbook_for_yaml_export(parent, cache)
        if parent_prep.get("unresolved_bindings"):
            sink.write_json("09b-parent-bindings.json", parent_prep)

    parent_yaml = dumps_yaml(
        parent,
        policy=policy,
        script_names=script_names,
        playbook_names=playbook_names,
        bind_subplaybooks_by_id=bind_by_id,
    )
    sink.write_text("09-parent-rewritten.yaml", parent_yaml)

    if mismatch and not args.upload_parent_on_mismatch and not args.upload_only:
        sink.log("Mismatch: not uploading parent copy (pass --upload-parent-on-mismatch to override)")
    elif should_upload_parent:
        sink.log(f"Uploading parent copy {parent_copy_name!r}")
        parent_upload = client.save_yaml(parent_yaml, filename=f"{slug(parent_copy_name)}.yml")
        cache.on_upload()
        sink.write_json("10-parent-upload.json", parent_upload)
        result["parent"]["upload"] = parent_upload

    if args.upload_only:
        return _finish_extract(args, client, cache, sink, result, exit_code=0, text="Upload-only complete.")
    return _finish_extract(args, client, cache, sink, result, exit_code=2 if mismatch else 0)


def _parse_cluster_ref(playbook: JsonDict, spec: str) -> tuple[str, str]:
    if ":" not in spec:
        raise ValueError(f"Cluster spec must be START:END, got {spec!r}")
    start_ref, end_ref = spec.split(":", 1)
    start_ref = start_ref.strip()
    end_ref = end_ref.strip()
    if not start_ref or not end_ref:
        raise ValueError(f"Cluster spec must be START:END, got {spec!r}")
    return resolve_task_ref(playbook, start_ref), resolve_task_ref(playbook, end_ref)


def _load_script_and_playbook_names(
    client: PlaybookClient,
    playbook: JsonDict,
    cache: PlaybookCache,
    sink: DebugSink,
) -> tuple[JsonDict, JsonDict]:
    script_names: JsonDict = {}
    playbook_names: JsonDict = {}
    try:
        script_names = client.script_id_to_name()
        sink.log(f"Loaded {len(script_names)} automation names for YAML scriptName mapping")
    except PlaybookApiError as exc:
        sink.log(f"Automation catalog unavailable ({exc}); using scriptId values as scriptName")
    for pid, pname in id_to_name_map(cache).items():
        playbook_names.setdefault(pid, pname)
    for node in playbook_tasks(playbook).values():
        if task_type(node) != "playbook":
            continue
        inner = inner_task(node)
        pid = str(get_field(inner, "playbookId") or "")
        pname = str(get_field(inner, "playbookName") or "")
        if pid and pname:
            playbook_names[pid] = pname
    return script_names, playbook_names


def cmd_extract_multi(args: argparse.Namespace) -> int:
    if getattr(args, "parallel", False):
        from .extract_multi_parallel import run_extract_multi_parallel

        return run_extract_multi_parallel(args)

    from .extract_multi_common import (
        finalize_extract_multi,
        prepare_extract_multi,
        upload_compare_subplaybooks_sequential,
    )

    state = prepare_extract_multi(args)
    early_exit = upload_compare_subplaybooks_sequential(state)
    if early_exit is not None:
        return early_exit
    return finalize_extract_multi(state, parallel_post_steps=False)


def cmd_validate_jobs(args: argparse.Namespace) -> int:
    _creds, client, cache, policy = _runtime(args)
    sink = _sink_for(args, "validate-jobs")
    paths = [Path(item) for item in args.jobs]
    jobs = merge_job_manifests(paths) if len(paths) > 1 else load_jobs(paths[0])
    sink.write_json("00-jobs.json", {"jobs": jobs})
    payload = validate_jobs(
        jobs,
        cache=cache,
        client=client,
        policy=policy,
        sink=sink,
        keep_failures=args.keep_failures,
        refresh_before=not args.no_refresh_before,
        refresh_after_deletes=not args.no_refresh_after_deletes,
        log=sink.log,
    )
    text_lines = [
        f"jobs: {payload['job_count']}",
        f"equal: {payload['equal']}",
        f"mismatch: {payload['mismatch']}",
        f"skipped: {payload['skipped']}",
        f"deleted_rows: {payload['deleted_rows']}",
    ]
    _emit(sink, args, payload, text="\n".join(text_lines))
    if payload["mismatch"] or payload["skipped"] or payload["delete_failures"]:
        return 2
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    _creds, client, cache, _policy = _runtime(args)
    prefix = args.name_prefix
    ids = list(args.playbooks or [])
    if not prefix and not ids:
        raise SystemExit("error: delete requires --playbook and/or --name-prefix")
    sink = _sink_for(args, f"delete-{prefix or 'playbooks'}")

    rows: list[JsonDict] = []
    seen: set[str] = set()
    if prefix:
        matches = cache.find_by_name_prefix(prefix, force=args.force)
        sink.write_json("01-prefix-matches.json", matches)
        for row in matches:
            pid = str(row.get("id") or "")
            key = pid or str(row.get("name") or "")
            if key and key not in seen:
                seen.add(key)
                rows.append(row)
    for ref in ids:
        playbook = cache.resolve(ref, force=args.force)
        pid = str(playbook.get("id") or "")
        key = pid or str(playbook.get("name") or "")
        if key and key not in seen:
            seen.add(key)
            rows.append({"id": pid, "name": playbook.get("name")})

    ordered = order_playbooks_for_delete(rows)
    sink.write_json("02-delete-order.json", ordered)
    outcomes = delete_playbook_rows(ordered, delete_fn=client.delete_playbook, log=sink.log)
    cache.on_delete()
    text = format_delete_text(outcomes, prefix=prefix)
    payload: JsonDict = {
        "name_prefix": prefix,
        "count": len(outcomes),
        "deleted": sum(1 for row in outcomes if row.get("ok")),
        "failed": sum(1 for row in outcomes if not row.get("ok")),
        "outcomes": outcomes,
    }
    sink.write_json("03-delete-outcomes.json", payload)
    _emit(sink, args, payload, text=text)
    return 1 if any(not row.get("ok") for row in outcomes) else 0


def cmd_update_playbook_tasks(args: argparse.Namespace) -> int:
    if (
        not args.updates
        and not args.context_updates
        and not args.match_task_names
    ):
        raise SystemExit(
            "error: at least one --update, --context-update, or --match-task-name is required"
        )
    if args.name_prefix:
        playbook_label = args.name_prefix
    elif args.playbook:
        playbook_label = args.playbook
    else:
        raise SystemExit("error: --playbook or --name-prefix is required")

    _creds, client, cache, policy = _runtime(args)
    sink = _sink_for(args, f"update-playbook-tasks-{playbook_label}")
    targets = _resolve_update_playbook_targets(args, cache)
    sink.write_json("00-targets.json", {"targets": [{"id": p.get("id"), "name": p.get("name")} for p in targets]})

    outcomes: List[JsonDict] = []
    for index, playbook in enumerate(targets, 1):
        playbook_name = str(playbook.get("name") or "")
        error_updates, error_rejected = _collect_error_updates_for_playbook(
            playbook,
            explicit_specs=args.updates or [],
            match_specs=args.match_task_names or [],
            match_actions=args.match_update,
        )
        context_updates_requested = [parse_context_update_spec(spec) for spec in args.context_updates or []]
        context_updates, context_rejected = preflight_context_updates(playbook, context_updates_requested)
        sink.write_json(f"{index:02d}-source-playbook.json", playbook)
        sink.write_json(
            f"{index:02d}-preflight.json",
            {"error_rejected": error_rejected, "context_rejected": context_rejected},
        )
        if not error_updates and not context_updates:
            outcomes.append(
                {
                    "playbook_name": playbook_name,
                    "ok": not error_rejected and not context_rejected,
                    "skipped": True,
                    "reason": "no applicable updates",
                    "error_rejected": error_rejected,
                    "context_rejected": context_rejected,
                }
            )
            continue
        outcome = overwrite_playbook_task_updates(
            client=client,
            cache=cache,
            policy=policy,
            playbook=playbook,
            error_updates=error_updates,
            context_updates=context_updates,
            sink=sink,
            dry_run=args.dry_run,
        )
        outcome["error_rejected"] = list(outcome.get("error_rejected") or []) + error_rejected
        outcome["context_rejected"] = list(outcome.get("context_rejected") or []) + context_rejected
        if error_rejected or context_rejected:
            outcome["ok"] = False
        sink.write_json(f"{index:02d}-outcome.json", outcome)
        outcomes.append(outcome)

    ok = all(row.get("ok") for row in outcomes)
    payload = {"target_count": len(targets), "ok": ok, "outcomes": outcomes}
    lines = [f"Targets: {len(targets)}", f"Outcome: {'OK' if ok else 'FAILED'}"]
    for row in outcomes:
        lines.append(
            f"  {row.get('playbook_name')}: "
            f"{'OK' if row.get('ok') else 'FAILED'}"
            f"{' (skipped)' if row.get('skipped') else ''}"
        )
    _emit(sink, args, payload, text="\n".join(lines))
    return 0 if ok else 2


cmd_update_error_retry = cmd_update_playbook_tasks


def _cmd_upload_yaml(args: argparse.Namespace, *, kind: str) -> int:
    if not args.credentials:
        raise SystemExit("error: --credentials is required for upload commands")
    creds, client, _cache, _policy = _runtime(args)
    paths = collect_yaml_paths(args.paths, recursive=bool(args.recursive))
    sink = _sink_for(args, f"upload-{kind}s-{'-'.join(Path(p).stem for p in paths[:3])}")
    outcomes = upload_many(client, paths, kind=kind)
    payload: JsonDict = {
        "platform": creds.platform.value,
        "kind": kind,
        "paths": [str(path) for path in paths],
        "outcomes": [item.to_dict() for item in outcomes],
    }
    sink.write_json("01-upload-outcomes.json", payload)
    text = format_upload_report(outcomes)
    sink.write_text("01-upload-outcomes.txt", text)
    _emit(sink, args, payload, text=text)
    ok_count = sum(1 for item in outcomes if item.ok)
    return 0 if ok_count == len(outcomes) else 1


def cmd_upload_playbooks(args: argparse.Namespace) -> int:
    return _cmd_upload_yaml(args, kind="playbook")


def cmd_upload_scripts(args: argparse.Namespace) -> int:
    return _cmd_upload_yaml(args, kind="script")


def cmd_list_lists(args: argparse.Namespace) -> int:
    if not args.credentials:
        raise SystemExit("error: --credentials is required for list-lists")
    creds = load_credentials(args.credentials, platform=args.tenant_type, verify_ssl=not args.insecure)
    client = PlaybookClient(creds)
    sink = _sink_for(args, "list-lists")
    records = list_all(client)
    needle = str(args.name_contains or "")
    if needle:
        records = [item for item in records if needle in item.name or needle in item.id]
    rows = [
        {
            "id": item.id,
            "name": item.name,
            "type": item.list_type,
            "version": item.version,
            "bytes": len(item.data.encode("utf-8")),
        }
        for item in sorted(records, key=lambda row: row.name.lower())
    ]
    payload: JsonDict = {"count": len(rows), "lists": rows}
    text = "\n".join(
        [f"Lists: {len(rows)}"]
        + [f"  {row['name']} [{row['id']}] type={row['type']} version={row['version']} bytes={row['bytes']}" for row in rows]
    )
    sink.write_json("01-lists.json", payload)
    sink.write_text("01-lists.txt", text)
    _emit(sink, args, payload, text=text)
    return 0


def cmd_copy_list(args: argparse.Namespace) -> int:
    if len(args.names) != 1 and args.target_name:
        raise SystemExit("error: --target-name is only valid when copying a single list")
    src_creds = load_credentials(
        args.from_credentials,
        platform=args.from_tenant_type,
        verify_ssl=not args.insecure,
    )
    dst_creds = load_credentials(
        args.to_credentials,
        platform=args.to_tenant_type,
        verify_ssl=not args.insecure,
    )
    source = PlaybookClient(src_creds)
    target = PlaybookClient(dst_creds)
    sink = _sink_for(args, f"copy-list-{'-'.join(args.names[:3])}")
    if len(args.names) == 1:
        from .lists import copy_list

        outcome = copy_list(
            source,
            target,
            args.names[0],
            target_name=args.target_name,
            overwrite=not args.no_overwrite,
            commit_message=args.commit_message,
        )
        outcomes = [outcome]
    else:
        outcomes = copy_lists(
            source,
            target,
            args.names,
            target_name_prefix=args.target_prefix,
            overwrite=not args.no_overwrite,
            commit_message=args.commit_message,
        )
    payload: JsonDict = {
        "from": src_creds.host,
        "to": dst_creds.host,
        "outcomes": [item.to_dict() for item in outcomes],
    }
    text = format_list_copy_report(outcomes)
    sink.write_json("01-copy-outcomes.json", payload)
    sink.write_text("01-copy-outcomes.txt", text)
    _emit(sink, args, payload, text=text)
    ok_count = sum(1 for item in outcomes if item.ok)
    return 0 if ok_count == len(outcomes) else 1


def cmd_discover_yaml_keys(args: argparse.Namespace) -> int:
    yaml_path = Path(args.yaml)
    if not yaml_path.is_file():
        print(f"Not found: YAML file {yaml_path}", file=sys.stderr)
        return 1
    sink = _sink_for(args, f"discover-yaml-keys-{yaml_path.stem}")
    yaml_text = yaml_path.read_text(encoding="utf-8")
    api_playbook = None
    if args.json:
        api_playbook = load_json_playbook(args.json)
    elif args.playbook:
        if not args.credentials:
            raise SystemExit("error: --credentials is required with --playbook")
        _creds, _client, cache, _policy = _runtime(args)
        api_playbook = cache.resolve(args.playbook, force=args.force)
        sink.write_json("01-api-playbook.json", api_playbook)
    result = discover_yaml_keys(yaml_text, api_playbook, task_ids=args.tasks)
    text = result.human_summary()
    sink.write_json("02-discover.json", result.to_dict())
    sink.write_text("02-discover.txt", text)
    _emit(sink, args, result.to_dict(), text=text)
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    commands = {
        "cache-status": cmd_cache_status,
        "cache-invalidate": cmd_cache_invalidate,
        "cache-refresh": cmd_cache_refresh,
        "list": cmd_list,
        "get": cmd_get,
        "check-root": cmd_check_root,
        "inspect": cmd_inspect,
        "search-task-inputs": cmd_search_task_inputs,
        "search-tasks": cmd_search_tasks,
        "search-task-outputs": cmd_search_task_outputs,
        "trace-branches": cmd_trace_branches,
        "show-task": cmd_show_task,
        "compare": cmd_compare,
        "extract": cmd_extract,
        "extract-multi": cmd_extract_multi,
        "validate-jobs": cmd_validate_jobs,
        "delete": cmd_delete,
        "discover-yaml-keys": cmd_discover_yaml_keys,
        "update-error-retry": cmd_update_error_retry,
        "update-playbook-tasks": cmd_update_playbook_tasks,
        "upload-playbooks": cmd_upload_playbooks,
        "upload-scripts": cmd_upload_scripts,
        "list-lists": cmd_list_lists,
        "copy-list": cmd_copy_list,
    }
    try:
        return commands[args.command](args)
    except PlaybookApiError as exc:
        print(f"API error: {exc}", file=sys.stderr)
        return 1
    except KeyError as exc:
        print(f"Not found: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
