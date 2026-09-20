"""Resolve playbook task bindings before YAML upload (aligned with bay/playbook-utils)."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Optional

from ..core.paths import uses_cortex_platform_content_api
from ..credentials import CredentialProfile, get_profile
from ..scripts.cache import script_index_maps
from .binding_enrichment import enrich_bindings_from_source_cache
from .bindings import resolve_playbook_task_bindings
from .entity_resolution import _mutable_inner, resolve_script_task_bindings
from .resolver import CachePlaybookResolver
from .yaml_helpers import task_field


def _script_index_maps(
    profile: CredentialProfile,
) -> tuple[dict[str, str], dict[str, str]]:
    script_by_id, _ = script_index_maps(profile)
    id_to_name = {
        script_id: str(item.get("name") or "")
        for script_id, item in script_by_id.items()
        if str(item.get("name") or "")
    }
    name_to_id = {
        str(item.get("name") or ""): script_id
        for script_id, item in script_by_id.items()
        if str(item.get("name") or "")
    }
    return id_to_name, name_to_id


def finalize_script_fields_for_yaml(
    playbook: MutableMapping[str, Any],
    *,
    bind_scripts_by_id: bool,
    name_to_id: Mapping[str, str],
) -> None:
    """On Cortex Platform tenants, automation tasks bind via target ``scriptId`` UUID."""
    if not bind_scripts_by_id:
        return
    for node in (playbook.get("tasks") or {}).values():
        if not isinstance(node, dict) or node.get("type") != "regular":
            continue
        inner = _mutable_inner(node)
        if inner.get("isCommand") is True:
            continue
        script_name = task_field(inner, "scriptName")
        if script_name and str(script_name) in name_to_id:
            inner["scriptId"] = str(name_to_id[str(script_name)])


def finalize_subplaybook_fields_for_yaml(
    playbook: MutableMapping[str, Any],
    *,
    bind_subplaybooks_by_id: bool,
) -> None:
    """Apply bay ``yaml_codec`` sub-playbook binding shape after cache resolution."""
    for node in (playbook.get("tasks") or {}).values():
        if not isinstance(node, dict) or node.get("type") != "playbook":
            continue
        inner = _mutable_inner(node)
        if bind_subplaybooks_by_id:
            playbook_id = task_field(inner, "playbookId")
            playbook_name = task_field(inner, "playbookName")
            if playbook_id:
                inner["playbookId"] = str(playbook_id)
            if playbook_name:
                inner["playbookName"] = str(playbook_name)
            continue
        inner.pop("playbookId", None)
        inner.pop("playbookid", None)


def prepare_playbook_bindings_for_upload(
    playbook: MutableMapping[str, Any],
    profile: CredentialProfile | str,
    *,
    source_profile: Optional[CredentialProfile | str] = None,
    playbook_name_to_id: Optional[Mapping[str, str]] = None,
    playbook_id_to_name: Optional[Mapping[str, str]] = None,
    script_id_remap: Optional[Mapping[str, str]] = None,
    playbook_id_remap: Optional[Mapping[str, str]] = None,
) -> list[dict[str, Any]]:
    """Resolve automation scripts and sub-playbooks against the target tenant cache."""
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    if source_profile is not None:
        enrich_bindings_from_source_cache(playbook, source_profile)
    script_id_to_name, script_name_to_id = _script_index_maps(resolved)

    if script_id_remap:
        for source_id, target_id in script_id_remap.items():
            target_name = script_id_to_name.get(str(target_id))
            if target_name:
                script_id_to_name[str(source_id)] = target_name

    playbook_resolver = CachePlaybookResolver(resolved)
    pb_name_to_id = dict(playbook_name_to_id or playbook_resolver.name_to_id())
    pb_id_to_name = dict(playbook_id_to_name or playbook_resolver.id_to_name())

    if playbook_id_remap:
        for source_id, target_id in playbook_id_remap.items():
            target_name = pb_id_to_name.get(str(target_id))
            if target_name:
                pb_id_to_name[str(source_id)] = target_name
                pb_name_to_id[target_name] = str(target_id)

    script_unresolved = resolve_script_task_bindings(
        playbook,
        id_to_name=script_id_to_name,
        name_to_id=script_name_to_id,
        script_id_remap=script_id_remap,
    )
    playbook_unresolved = resolve_playbook_task_bindings(
        playbook,
        name_to_id=pb_name_to_id,
        id_to_name=pb_id_to_name,
        playbook_id_remap=playbook_id_remap,
    )

    bind_by_id = uses_cortex_platform_content_api(resolved.tenant_type)
    finalize_script_fields_for_yaml(
        playbook,
        bind_scripts_by_id=bind_by_id,
        name_to_id=script_name_to_id,
    )
    finalize_subplaybook_fields_for_yaml(
        playbook,
        bind_subplaybooks_by_id=bind_by_id,
    )
    return script_unresolved + playbook_unresolved
