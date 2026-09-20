"""Parallel cache refresh across scopes for one credential profile."""

from __future__ import annotations

from typing import Any, Callable, Iterable

from ..cache.refresh import run_cache_refresh
from ..credentials import CredentialProfile, get_profile
from ..integrations.cache import load_scope_cache
from ..lists.cache import load_lists_index
from ..lists.service import refresh_lists_cache
from ..playbooks.cache import load_playbooks_index
from ..playbooks.service import refresh_playbooks_cache
from ..runtime.graph import GraphExecutor, GraphRunResult, RefreshMode, Task, TaskGraph
from ..runtime.limits import profile_host_key
from ..scripts.cache import load_scripts_index
from ..scripts.service import refresh_scripts_cache


ScopeRefresh = tuple[str, Callable[[CredentialProfile], dict[str, Any]], Callable[[CredentialProfile], dict[str, Any]]]

_CONTENT_SCOPES: dict[str, ScopeRefresh] = {
    "playbooks": ("playbooks", load_playbooks_index, refresh_playbooks_cache),
    "scripts": ("scripts", load_scripts_index, refresh_scripts_cache),
    "lists": ("lists", load_lists_index, refresh_lists_cache),
}

def _integration_refresh_fn(scope: str) -> Callable[[CredentialProfile], dict[str, Any]]:
    from ..integrations.service import (
        refresh_installed_packs,
        refresh_integration_commands,
        refresh_integration_instances,
        refresh_tenant_credentials_cache,
    )

    refresh_map = {
        "commands": refresh_integration_commands,
        "instances": refresh_integration_instances,
        "tenant_credentials": refresh_tenant_credentials_cache,
        "contentpacks": refresh_installed_packs,
    }
    refresh_fn = refresh_map.get(scope)
    if refresh_fn is None:
        raise ValueError(f"Unknown integration cache scope: {scope!r}")
    return refresh_fn


def _integration_load_index(profile: CredentialProfile, scope: str) -> dict[str, Any]:
    return load_scope_cache(profile, scope)


def refresh_content_scopes_parallel(
    profile: CredentialProfile | str,
    scopes: Iterable[str],
    *,
    mode: RefreshMode = RefreshMode.REQUIRED,
) -> GraphRunResult:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    graph = TaskGraph()
    host = profile_host_key(resolved)
    for scope in scopes:
        entry = _CONTENT_SCOPES.get(scope)
        if entry is None:
            raise ValueError(f"Unknown content cache scope: {scope!r}")
        scope_name, load_index, refresh = entry

        def _make_fn(
            s: str = scope_name,
            load: Callable = load_index,
            ref: Callable = refresh,
        ) -> Callable[[], dict[str, Any]]:
            return lambda: run_cache_refresh(
                resolved,
                s,
                load_index=load,
                refresh=ref,
                mode=mode,
            )

        graph.add(
            Task(
                id=scope_name,
                fn=_make_fn(),
                profile_slug=resolved.slug,
                host_key=host,
            )
        )
    return GraphExecutor().run(graph)


def refresh_integrations_scopes_parallel(
    profile: CredentialProfile | str,
    scopes: Iterable[str],
    *,
    mode: RefreshMode = RefreshMode.REQUIRED,
) -> GraphRunResult:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    graph = TaskGraph()
    host = profile_host_key(resolved)
    for scope in scopes:
        refresh_fn = _integration_refresh_fn(scope)

        def _make_fn(
            s: str = scope,
            ref: Callable = refresh_fn,
        ) -> Callable[[], dict[str, Any]]:
            return lambda: run_cache_refresh(
                resolved,
                s,
                load_index=lambda p, sc=s: _integration_load_index(p, sc),
                refresh=ref,
                mode=mode,
            )

        graph.add(
            Task(
                id=scope,
                fn=_make_fn(),
                profile_slug=resolved.slug,
                host_key=host,
            )
        )
    return GraphExecutor().run(graph)


def graph_result_to_dict(result: GraphRunResult) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": result.ok, "scopes": {}}
    for task_id, state in result.tasks.items():
        entry: dict[str, Any] = {"status": state.status}
        if state.status == "success":
            entry["result"] = state.result
        else:
            entry["error"] = state.error
            if state.failed_dependencies:
                entry["failed_dependencies"] = state.failed_dependencies
        payload["scopes"][task_id] = entry
    return payload


def ws_scope_names(scope: str) -> list[str]:
    normalized = scope.lower()
    if normalized == "all":
        return ["playbooks", "scripts", "lists", "integrations"]
    if normalized == "playbooks+scripts":
        return ["playbooks", "scripts"]
    if normalized in _CONTENT_SCOPES or normalized == "integrations":
        return [normalized]
    raise ValueError(f"Unknown cache refresh scope: {scope!r}")
