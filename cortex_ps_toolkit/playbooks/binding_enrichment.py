"""Fill missing task binding names from the source tenant cache before target rebinding."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping

from ..credentials import CredentialProfile, get_profile
from ..scripts.cache import script_index_maps
from .entity_resolution import _is_integration_command, _mutable_inner, script_binding_candidates
from .resolver import CachePlaybookResolver
from .yaml_helpers import is_script_uuid, script_name_from_task, set_canonical, task_field


def _source_script_id_to_name(profile: CredentialProfile) -> Mapping[str, str]:
    script_by_id, _ = script_index_maps(profile)
    return {
        script_id: str(item.get("name") or "")
        for script_id, item in script_by_id.items()
        if str(item.get("name") or "")
    }


def enrich_bindings_from_source_cache(
    playbook: MutableMapping[str, Any],
    source: CredentialProfile | str,
) -> None:
    """Set ``playbookName`` / ``scriptName`` on tasks when only source UUIDs are present."""
    resolved = get_profile(source) if isinstance(source, str) else source
    source_playbook_id_to_name = CachePlaybookResolver(resolved).id_to_name()
    source_script_id_to_name = _source_script_id_to_name(resolved)

    for node in (playbook.get("tasks") or {}).values():
        if not isinstance(node, dict):
            continue
        task_type = str(node.get("type") or "")
        if task_type == "playbook":
            inner = _mutable_inner(node)
            playbook_id = task_field(inner, "playbookId")
            playbook_name = task_field(inner, "playbookName")
            if playbook_id and not playbook_name:
                resolved_name = source_playbook_id_to_name.get(str(playbook_id))
                if resolved_name:
                    set_canonical(inner, "playbookName", resolved_name)
            continue

        if task_type != "regular":
            continue

        inner = _mutable_inner(node)
        if not inner:
            continue
        candidates = script_binding_candidates(inner)
        if candidates and _is_integration_command(inner, candidates[0]):
            continue

        script_name = script_name_from_task(node) or task_field(inner, "scriptName")
        if script_name:
            continue

        script_id = task_field(inner, "scriptId")
        binding = candidates[0] if candidates else None
        lookup_id = None
        if script_id and is_script_uuid(str(script_id)):
            lookup_id = str(script_id)
        elif binding and is_script_uuid(str(binding)):
            lookup_id = str(binding)

        if lookup_id:
            resolved_name = source_script_id_to_name.get(lookup_id)
            if resolved_name:
                set_canonical(inner, "scriptName", resolved_name)
