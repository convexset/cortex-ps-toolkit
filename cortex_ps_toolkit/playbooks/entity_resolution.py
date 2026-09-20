"""Resolve playbook task bindings to tenant cache entities (analysis + copy).

Patterns aligned with bay/playbook-utils: ``playbookName`` / cache name lookup is
authoritative for sub-playbooks; script UUIDs map through the scripts index; integration
commands (``Brand|||command``) are not custom automations for copy scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, MutableMapping, Optional

from .resolver import CachePlaybookResolver
from .yaml_helpers import (
    is_script_uuid,
    playbook_identity,
    resolve_script_binding,
    script_name_from_task,
    set_canonical,
    sub_playbook_reference,
    task_field,
)

ScriptKind = Literal["automation", "integration_command"]


@dataclass(frozen=True)
class ScriptReference:
    kind: ScriptKind
    canonical_name: str
    script_id: Optional[str]
    command_display: str
    command_raw: Optional[str]
    resolved: bool
    binding: str


def _mutable_inner(node: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    task = node.get("task")
    if not isinstance(task, dict):
        task = {}
        node["task"] = task
    return task


def script_binding_candidates(inner: Mapping[str, Any]) -> list[str]:
    inner_dict = dict(inner)
    candidates: list[str] = []
    for field in ("script", "scriptId", "scriptName"):
        value = inner_dict.get("script") if field == "script" else task_field(inner_dict, field)
        if value:
            text = str(value).strip()
            if text and text not in candidates:
                candidates.append(text)
    return candidates


def _is_integration_command(inner: Mapping[str, Any], binding: str) -> bool:
    if inner.get("isCommand") is True:
        return True
    if "|||" in binding:
        brand = binding.split("|||", 1)[0].strip()
        return not is_script_uuid(brand)
    return False


def integration_command_from_task(
    node: Mapping[str, Any],
    *,
    script_by_id: Mapping[str, Mapping[str, Any]],
) -> Optional[dict[str, Any]]:
    """Return integration command metadata when the task is not a custom automation."""
    if str(node.get("type") or "") != "regular":
        return None
    inner = dict(node.get("task") or {})
    candidates = script_binding_candidates(inner)
    if not candidates:
        return None
    binding = next((c for c in candidates if _is_integration_command(inner, c)), None)
    if not binding:
        return None
    hint = script_name_from_task(dict(node))
    display, raw = resolve_script_binding(binding, script_by_id=script_by_id, name_hint=hint)
    return {
        "command": display,
        "raw": raw if raw and raw != display else None,
        "resolved": True,
        "copy_required": False,
    }


def resolve_automation_script(
    node: Mapping[str, Any],
    *,
    script_by_id: Mapping[str, Mapping[str, Any]],
    script_by_name: Mapping[str, Mapping[str, Any]],
) -> Optional[ScriptReference]:
    """Resolve a regular task to a tenant automation script (copy scope)."""
    if str(node.get("type") or "") != "regular":
        return None

    inner = dict(node.get("task") or {})
    if inner.get("isCommand") is True:
        return None

    name_hint = script_name_from_task(dict(node))
    candidates = script_binding_candidates(inner)
    canonical_name: Optional[str] = None
    script_id: Optional[str] = None
    primary_binding: Optional[str] = None

    if name_hint:
        canonical_name = name_hint
        entry = script_by_name.get(name_hint)
        if entry:
            script_id = str(entry.get("id") or "") or None
        for candidate in candidates:
            if is_script_uuid(candidate):
                primary_binding = candidate
                entry = script_by_id.get(candidate)
                if entry:
                    canonical_name = str(entry.get("name") or name_hint)
                    script_id = str(entry.get("id") or candidate)
                break

    if not canonical_name:
        for candidate in candidates:
            if _is_integration_command(inner, candidate):
                continue
            if is_script_uuid(candidate):
                entry = script_by_id.get(candidate)
                if entry:
                    canonical_name = str(entry.get("name") or "")
                    script_id = str(entry.get("id") or candidate)
                    primary_binding = candidate
                    break
            elif candidate in script_by_name:
                entry = script_by_name[candidate]
                canonical_name = str(entry.get("name") or candidate)
                script_id = str(entry.get("id") or "") or None
                primary_binding = candidate
                break
            elif not is_script_uuid(candidate):
                canonical_name = candidate
                entry = script_by_name.get(candidate)
                script_id = str(entry.get("id") or "") or None if entry else None
                primary_binding = candidate
                break

    if not canonical_name:
        return None

    display, raw = resolve_script_binding(
        primary_binding or canonical_name,
        script_by_id=script_by_id,
        name_hint=canonical_name,
    )
    resolved = bool(script_id) or canonical_name in script_by_name
    return ScriptReference(
        kind="automation",
        canonical_name=canonical_name,
        script_id=script_id,
        command_display=display or canonical_name,
        command_raw=raw if raw and raw != (display or canonical_name) else None,
        resolved=resolved,
        binding=primary_binding or canonical_name,
    )


def resolve_regular_task_script(
    node: Mapping[str, Any],
    *,
    script_by_id: Mapping[str, Mapping[str, Any]],
    script_by_name: Mapping[str, Mapping[str, Any]],
) -> Optional[ScriptReference]:
    """Backward-compatible alias: automation script resolution for a regular task."""
    return resolve_automation_script(node, script_by_id=script_by_id, script_by_name=script_by_name)


def sub_playbook_display_name(
    resolver: CachePlaybookResolver,
    playbook_id: Optional[str],
    playbook_name: Optional[str],
) -> tuple[str, Optional[str], bool]:
    """Return ``(display_name, resolved_id, missing)`` for a sub-playbook reference."""
    target = resolver.resolve(playbook_id, playbook_name)
    if target:
        playbook = resolver.load(target)
        _, cached_name = playbook_identity(playbook)
        display = cached_name or playbook_name or playbook_id or "unknown sub-playbook"
        return display, target, False
    lookup = playbook_name or playbook_id or "unknown sub-playbook"
    return str(lookup), None, True


def resolve_script_task_bindings(
    playbook: MutableMapping[str, Any],
    *,
    id_to_name: Mapping[str, str],
    name_to_id: Mapping[str, str],
    script_id_remap: Optional[Mapping[str, str]] = None,
) -> list[dict[str, Any]]:
    """Rewrite automation script UUID bindings to ``scriptName`` for YAML upload."""
    unresolved: list[dict[str, Any]] = []

    for task_id, node in (playbook.get("tasks") or {}).items():
        if node.get("type") != "regular":
            continue
        inner = _mutable_inner(node)
        if not inner:
            continue

        candidates = script_binding_candidates(inner)
        if not candidates:
            continue

        binding = candidates[0]
        if script_id_remap and binding in script_id_remap:
            binding = script_id_remap[binding]
        if _is_integration_command(inner, binding):
            set_canonical(inner, "script", binding)
            inner.pop("scriptId", None)
            inner.pop("scriptid", None)
            inner.pop("scriptName", None)
            inner.pop("scriptname", None)
            set_canonical(inner, "isCommand", True)
            continue

        script_id = task_field(inner, "scriptId") or (
            binding if is_script_uuid(binding) else None
        )
        if script_id and script_id_remap and str(script_id) in script_id_remap:
            script_id = script_id_remap[str(script_id)]
        script_name = script_name_from_task(node) or inner.get("scriptName")

        canonical_name = script_name
        if script_id and str(script_id) in id_to_name:
            canonical_name = id_to_name[str(script_id)]
        elif script_id and not is_script_uuid(str(script_id)) and str(script_id) in name_to_id:
            canonical_name = str(script_id)
        elif script_name and script_name in name_to_id:
            canonical_name = script_name
        elif script_id and is_script_uuid(str(script_id)) and script_name:
            canonical_name = script_name
        elif script_id and is_script_uuid(str(script_id)):
            unresolved.append({
                "task_id": task_id,
                "script_id": str(script_id),
                "error": "script id not in target cache and no scriptName to re-resolve",
            })
            continue
        elif binding in name_to_id:
            canonical_name = binding
        else:
            canonical_name = script_name or (binding if not is_script_uuid(binding) else None)

        if not canonical_name:
            unresolved.append({
                "task_id": task_id,
                "binding": binding,
                "error": "could not resolve automation script binding",
            })
            continue

        set_canonical(inner, "scriptName", str(canonical_name))
        inner.pop("script", None)
        inner.pop("scriptId", None)
        inner.pop("scriptid", None)
        set_canonical(inner, "isCommand", False)

    return unresolved
