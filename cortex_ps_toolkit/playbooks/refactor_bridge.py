"""Bridge to bay/playbook-utils for live playbook refactor operations."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from ..credentials import CredentialProfile, get_profile
from ..paths import data_dir, package_root
from ..platforms import assert_operation_supported

_PB_UTILS_CACHE_SUBDIR = "playbook-utils-cache"


def playbook_utils_root() -> Path:
    raw = os.environ.get("CORTEX_PS_PLAYBOOK_UTILS_PATH", "").strip()
    if raw:
        path = Path(raw).expanduser().resolve()
    else:
        path = (package_root().parent / "bay" / "playbook-utils").resolve()
    if not (path / "playbook_utils").is_dir():
        raise RuntimeError(
            f"bay/playbook-utils not found at {path}. "
            "Clone the repo sibling or set CORTEX_PS_PLAYBOOK_UTILS_PATH."
        )
    return path


def playbook_utils_cache_dir() -> Path:
    return data_dir() / _PB_UTILS_CACHE_SUBDIR


def playbook_utils_job_cache_dir(job_cache_key: str) -> Path:
    """Return an isolated playbook-utils cache directory for one refactor job."""
    safe = re.sub(r"[^\w./-]+", "-", job_cache_key.strip()).strip("-./")
    safe = safe.replace("/", os.sep)
    if not safe:
        raise ValueError("job_cache_key must contain at least one safe character")
    path = (playbook_utils_cache_dir() / "jobs" / safe).resolve()
    base = playbook_utils_cache_dir().resolve()
    if not str(path).startswith(str(base)):
        raise ValueError(f"Refusing unsafe job_cache_key: {job_cache_key!r}")
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_playbook_utils_cache_dir(job_cache_key: Optional[str] = None) -> Path:
    if job_cache_key:
        return playbook_utils_job_cache_dir(job_cache_key)
    return playbook_utils_cache_dir()


def _ensure_imported() -> None:
    root = str(playbook_utils_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def profile_credentials_payload(profile: CredentialProfile) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "url": profile.url,
        "key": profile.key,
        "tenant_type": profile.tenant_type.value,
    }
    if profile.api_id:
        payload["api_id"] = profile.api_id
    payload["verify"] = profile.verify_ssl
    return payload


@contextmanager
def temporary_credentials_file(profile: CredentialProfile) -> Iterator[Path]:
    payload = profile_credentials_payload(profile)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix=f"credentials-{profile.slug}-",
        delete=False,
        encoding="utf-8",
    ) as handle:
        json.dump(payload, handle, indent=2)
        path = Path(handle.name)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def build_extract_multi_args(
    *,
    credentials_path: str,
    profile: CredentialProfile,
    playbook: str,
    leaf_tasks: Optional[list[str]] = None,
    clusters: Optional[list[str]] = None,
    post_task_updates: Optional[list[str]] = None,
    parent_copy_name: Optional[str] = None,
    debug_dir: Optional[str] = None,
    damp_run: bool = False,
    upload_only: bool = False,
    upload_parent_on_mismatch: bool = False,
    require_match: bool = False,
    force: bool = False,
    padding: float = 400.0,
    quiet: bool = True,
    parallel: bool = False,
    parallel_workers: Optional[int] = None,
    on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
    cache_dir: Optional[str | Path] = None,
    job_cache_key: Optional[str] = None,
) -> argparse.Namespace:
    resolved_cache_dir = resolve_playbook_utils_cache_dir(job_cache_key) if job_cache_key else (
        Path(cache_dir).expanduser().resolve() if cache_dir else playbook_utils_cache_dir()
    )
    return argparse.Namespace(
        credentials=credentials_path,
        tenant_type=profile.tenant_type.value,
        insecure=not profile.verify_ssl,
        cache_dir=str(resolved_cache_dir),
        cache_ttl=3600,
        fields_config=None,
        quiet=quiet,
        print_json=False,
        debug_dir=debug_dir,
        command="extract-multi",
        playbook=playbook,
        tasks=list(leaf_tasks or []),
        clusters=list(clusters or []),
        post_task_updates=list(post_task_updates or []),
        parent_copy_name=parent_copy_name,
        damp_run=damp_run,
        upload_only=upload_only,
        upload_parent_on_mismatch=upload_parent_on_mismatch,
        require_match=require_match,
        force=force,
        padding=padding,
        parallel=parallel,
        parallel_workers=parallel_workers,
    )


def build_update_tasks_args(
    *,
    credentials_path: str,
    profile: CredentialProfile,
    playbook: Optional[str] = None,
    name_prefix: Optional[str] = None,
    updates: Optional[list[str]] = None,
    context_updates: Optional[list[str]] = None,
    match_task_names: Optional[list[str]] = None,
    match_update: Optional[str] = None,
    debug_dir: Optional[str] = None,
    dry_run: bool = False,
    force: bool = False,
    quiet: bool = True,
) -> argparse.Namespace:
    return argparse.Namespace(
        credentials=credentials_path,
        tenant_type=profile.tenant_type.value,
        insecure=not profile.verify_ssl,
        cache_dir=str(playbook_utils_cache_dir()),
        cache_ttl=3600,
        fields_config=None,
        quiet=quiet,
        print_json=False,
        debug_dir=debug_dir,
        command="update-playbook-tasks",
        playbook=playbook,
        name_prefix=name_prefix,
        updates=list(updates or []),
        context_updates=list(context_updates or []),
        match_task_names=list(match_task_names or []),
        match_update=match_update,
        dry_run=dry_run,
        force=force,
    )


@contextmanager
def playbook_utils_runtime(
    profile_slug: str,
    *,
    operation_id: str,
    cache_dir: Optional[str | Path] = None,
    job_cache_key: Optional[str] = None,
) -> Iterator[tuple[CredentialProfile, Any, Any, Any, Any]]:
    """Yield (profile, creds, client, cache, policy) after importing playbook_utils."""
    _ensure_imported()
    from playbook_utils.cache import PlaybookCache
    from playbook_utils.client import PlaybookClient
    from playbook_utils.credentials import load_credentials
    from playbook_utils.fields import load_policy_file

    profile = get_profile(profile_slug)
    assert_operation_supported(operation_id, profile.tenant_type)

    resolved_cache_dir = resolve_playbook_utils_cache_dir(job_cache_key) if job_cache_key else (
        Path(cache_dir).expanduser().resolve() if cache_dir else playbook_utils_cache_dir()
    )

    with temporary_credentials_file(profile) as cred_path:
        creds = load_credentials(str(cred_path), platform=profile.tenant_type.value, verify_ssl=profile.verify_ssl)
        client = PlaybookClient(creds)
        cache = PlaybookCache(creds, client, resolved_cache_dir)
        policy = load_policy_file(None)
        yield profile, creds, client, cache, policy


@contextmanager
def progress_debug_sink(on_progress: Optional[Callable[[dict[str, Any]], None]]) -> Iterator[None]:
    """Forward playbook-utils DebugSink.log lines to *on_progress*."""
    if not on_progress:
        yield
        return
    _ensure_imported()
    from playbook_utils import debugio

    original_log = debugio.DebugSink.log

    def patched_log(self, message: str) -> None:
        original_log(self, message)
        on_progress({"phase": "log", "message": message})

    debugio.DebugSink.log = patched_log
    try:
        yield
    finally:
        debugio.DebugSink.log = original_log


def read_debug_result(debug_dir: Path) -> dict[str, Any]:
    result_path = debug_dir / "00-result.json"
    if not result_path.is_file():
        return {"debug_dir": str(debug_dir), "result_file_missing": True}
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload.setdefault("debug_dir", str(debug_dir))
        return payload
    return {"debug_dir": str(debug_dir), "result": payload}
