"""Integration cache refresh orchestration."""

from __future__ import annotations

from typing import Any, Optional

from ..cache.refresh import run_cache_refresh
from ..credentials import CredentialProfile, get_profile
from ..ops_log import op_info
from ..platforms import UnsupportedOperation
from ..runtime.graph import RefreshMode
from ..workflows.cache_refresh import refresh_integrations_scopes_parallel
from . import api
from .cache import load_scope_cache, write_scope_cache
from .detail import index_command_bodies, index_configuration_bodies, index_instance_bodies
from .sanitize import sanitize_search_payload


def _command_index_row(item: dict[str, Any]) -> dict[str, Any]:
    commands = item.get("commands") or []
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or ""),
        "display": str(item.get("display") or ""),
        "category": str(item.get("category") or ""),
        "feed": item.get("feed") is True,
        "command_count": len(commands) if isinstance(commands, list) else 0,
    }


def _instance_index_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or ""),
        "brand": str(item.get("brand") or ""),
        "category": str(item.get("category") or ""),
        "enabled": str(item.get("enabled") or ""),
        "engine": str(item.get("engine") or ""),
        "pack_id": item.get("packID") or item.get("packId"),
        "pack_name": item.get("packName"),
        "system": item.get("isSystemIntegration") is True or item.get("isBuiltin") is True,
        "hidden": item.get("hidden") is True,
    }


def _configuration_index_row(item: dict[str, Any], *, instance_count: int = 0) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or ""),
        "display": str(item.get("display") or item.get("name") or ""),
        "brand": str(item.get("brand") or ""),
        "category": str(item.get("category") or ""),
        "pack_id": item.get("packID") or item.get("packId"),
        "pack_name": item.get("packName"),
        "system": item.get("system") is True,
        "hidden": item.get("hidden") is True,
        "has_script": bool(str((item.get("integrationScript") or {}).get("script") or "").strip()),
        "instance_count": instance_count,
    }


def _instance_counts_by_brand(instances: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for instance in instances:
        brand = str(instance.get("brand") or "")
        if not brand:
            continue
        counts[brand] = counts.get(brand, 0) + 1
    return counts


def _credential_index_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or ""),
        "user": str(item.get("user") or ""),
        "workgroup": str(item.get("workgroup") or ""),
        "has_password": item.get("hasPassword") is True,
        "has_certificate": item.get("hasCertificate") is True,
        "has_certificate_pass": item.get("hasCertificatePass") is True,
        "vault_instance_id": item.get("vaultInstanceId"),
        "locked": item.get("locked") is True,
        "modified": item.get("modified"),
    }


def refresh_integration_commands(profile: CredentialProfile | str) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    op_info("Fetching integration commands for %s", resolved.slug)
    result = api.fetch_integration_commands(resolved)
    raw_integrations = [item for item in result.data if isinstance(item, dict)]
    rows = [_command_index_row(item) for item in raw_integrations]
    path = write_scope_cache(
        resolved,
        "commands",
        {
            "endpoint": result.endpoint,
            "status_code": result.status_code,
            "count": len(rows),
            "integrations": rows,
            "integration_bodies": index_command_bodies(raw_integrations),
        },
    )
    return {
        "profile": resolved.slug,
        "scope": "commands",
        "count": len(rows),
        "cache_path": str(path),
        "refreshed_at": load_scope_cache(resolved, "commands").get("refreshed_at"),
        "endpoint": result.endpoint,
    }


def refresh_integration_instances(profile: CredentialProfile | str) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    op_info("Fetching integration instances for %s", resolved.slug)
    result = api.fetch_integration_search(resolved)
    sanitized = sanitize_search_payload(result.data)
    raw_instances = [item for item in (sanitized.get("instances") or []) if isinstance(item, dict)]
    raw_configurations = [
        item for item in (sanitized.get("configurations") or []) if isinstance(item, dict)
    ]
    instance_counts = _instance_counts_by_brand(raw_instances)
    instances = [_instance_index_row(item) for item in raw_instances]
    configurations = [
        _configuration_index_row(
            item,
            instance_count=instance_counts.get(str(item.get("name") or ""), 0),
        )
        for item in raw_configurations
    ]
    path = write_scope_cache(
        resolved,
        "instances",
        {
            "endpoint": result.endpoint,
            "status_code": result.status_code,
            "instance_count": len(instances),
            "configuration_count": len(configurations),
            "instances": instances,
            "configurations": configurations,
            "configuration_bodies": index_configuration_bodies(raw_configurations),
            "instance_bodies": index_instance_bodies(raw_instances),
        },
    )
    return {
        "profile": resolved.slug,
        "scope": "instances",
        "instance_count": len(instances),
        "configuration_count": len(configurations),
        "cache_path": str(path),
        "refreshed_at": load_scope_cache(resolved, "instances").get("refreshed_at"),
        "endpoint": result.endpoint,
    }


def refresh_tenant_credentials_cache(profile: CredentialProfile | str) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    op_info("Fetching tenant credentials metadata for %s", resolved.slug)
    result = api.fetch_tenant_credentials(resolved)
    credentials = [
        _credential_index_row(item)
        for item in (result.data.get("credentials") or [])
        if isinstance(item, dict)
    ]
    path = write_scope_cache(
        resolved,
        "tenant_credentials",
        {
            "endpoint": result.endpoint,
            "status_code": result.status_code,
            "total": result.data.get("total", len(credentials)),
            "credentials": credentials,
        },
    )
    return {
        "profile": resolved.slug,
        "scope": "tenant_credentials",
        "count": len(credentials),
        "cache_path": str(path),
        "refreshed_at": load_scope_cache(resolved, "tenant_credentials").get("refreshed_at"),
        "endpoint": result.endpoint,
    }


def refresh_installed_packs(profile: CredentialProfile | str) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    op_info("Fetching installed content packs for %s", resolved.slug)
    result = api.fetch_installed_packs(resolved)
    packs = [
        {
            "id": str(item.get("id") or ""),
            "name": str(item.get("name") or ""),
            "current_version": item.get("currentVersion"),
            "last_install_date": item.get("lastInstallDate"),
            "update_available": item.get("updateAvailable") is True,
        }
        for item in result.data
        if isinstance(item, dict)
    ]
    path = write_scope_cache(
        resolved,
        "contentpacks",
        {
            "endpoint": result.endpoint,
            "status_code": result.status_code,
            "count": len(packs),
            "packs": packs,
        },
    )
    return {
        "profile": resolved.slug,
        "scope": "contentpacks",
        "count": len(packs),
        "cache_path": str(path),
        "refreshed_at": load_scope_cache(resolved, "contentpacks").get("refreshed_at"),
        "endpoint": result.endpoint,
    }


def _integration_scope_result(scope: str, state) -> dict[str, Any]:
    if state.status == "success":
        return state.result
    error = state.error or "refresh failed"
    if state.failed_dependencies:
        return {
            "skipped": True,
            "reason": error,
            "failed_dependencies": state.failed_dependencies,
        }
    return {"skipped": True, "reason": error}


def refresh_integrations_cache(
    profile: CredentialProfile | str,
    *,
    include_packs: bool = True,
    include_tenant_credentials: bool = True,
) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    scopes = ["commands", "instances"]
    if include_tenant_credentials:
        scopes.append("tenant_credentials")
    if include_packs:
        scopes.append("contentpacks")

    graph_result = refresh_integrations_scopes_parallel(
        resolved,
        scopes,
        mode=RefreshMode.REQUIRED,
    )
    results: dict[str, Any] = {"profile": resolved.slug}
    for scope in scopes:
        state = graph_result.tasks.get(scope)
        if state is None:
            continue
        if state.status == "success":
            results[scope] = state.result
            continue
        if scope in ("tenant_credentials", "contentpacks"):
            results[scope] = {"skipped": True, "reason": state.error or "refresh failed"}
            continue
        results[scope] = _integration_scope_result(scope, state)
    return results


def refresh_integration_scope(
    profile: CredentialProfile | str,
    scope: str,
    *,
    mode: RefreshMode = RefreshMode.REQUIRED,
) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    refresh_map = {
        "commands": refresh_integration_commands,
        "instances": refresh_integration_instances,
        "tenant_credentials": refresh_tenant_credentials_cache,
        "contentpacks": refresh_installed_packs,
    }
    refresh_fn = refresh_map.get(scope)
    if refresh_fn is None:
        raise ValueError(f"Unknown integration scope: {scope!r}")
    return run_cache_refresh(
        resolved,
        scope,
        load_index=lambda p, s=scope: load_scope_cache(p, s),
        refresh=refresh_fn,
        mode=mode,
    )


def list_cached_integration_configurations(profile: CredentialProfile | str) -> list[dict[str, Any]]:
    data = load_scope_cache(profile, "instances")
    return [item for item in (data.get("configurations") or []) if isinstance(item, dict)]


def find_configuration_in_cache(
    profile: CredentialProfile | str,
    integration_id: str,
) -> Optional[dict[str, Any]]:
    needle = str(integration_id)
    for item in list_cached_integration_configurations(profile):
        if str(item.get("id") or "") == needle or str(item.get("name") or "") == needle:
            return item
    return None


def get_integration_by_name(profile: CredentialProfile | str, name: str) -> Optional[dict[str, Any]]:
    for item in list_cached_integration_configurations(profile):
        if str(item.get("name") or "") == name:
            return item
    return None


def list_cached_integration_commands(profile: CredentialProfile | str) -> list[dict[str, Any]]:
    data = load_scope_cache(profile, "commands")
    return [item for item in (data.get("integrations") or []) if isinstance(item, dict)]


def list_cached_integration_instances(profile: CredentialProfile | str) -> dict[str, Any]:
    data = load_scope_cache(profile, "instances")
    return {
        "refreshed_at": data.get("refreshed_at"),
        "instances": [item for item in (data.get("instances") or []) if isinstance(item, dict)],
        "configurations": [
            item for item in (data.get("configurations") or []) if isinstance(item, dict)
        ],
    }


def list_cached_tenant_credentials(profile: CredentialProfile | str) -> list[dict[str, Any]]:
    data = load_scope_cache(profile, "tenant_credentials")
    return [item for item in (data.get("credentials") or []) if isinstance(item, dict)]


def list_cached_installed_packs(profile: CredentialProfile | str) -> list[dict[str, Any]]:
    data = load_scope_cache(profile, "contentpacks")
    return [item for item in (data.get("packs") or []) if isinstance(item, dict)]
