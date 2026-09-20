"""Playbook YAML task helpers (aligned with ai/tools/playbook_yaml/lib.py)."""

from __future__ import annotations

import re
from typing import Any, Iterator, Mapping, Optional, Tuple

JsonDict = dict[str, Any]

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "playbookId": ("playbookId", "playbookid"),
    "playbookName": ("playbookName", "playbookname"),
    "scriptId": ("scriptId", "scriptid"),
    "scriptName": ("scriptName", "scriptname"),
}


def task_field(task: JsonDict, field: str, default: Any = None) -> Any:
    keys = _KEY_ALIASES.get(field, (field,))
    for key in keys:
        if key in task:
            return task[key]
    return default


def playbook_identity(playbook: JsonDict) -> tuple[str, str]:
    return str(playbook.get("id") or ""), str(playbook.get("name") or "")


def sub_playbook_reference(inner_task: JsonDict) -> tuple[Optional[str], Optional[str]]:
    playbook_id = task_field(inner_task, "playbookId")
    playbook_name = task_field(inner_task, "playbookName")
    pid = str(playbook_id) if playbook_id else None
    pname = str(playbook_name) if playbook_name else None
    return pid, pname


def iter_sub_playbook_refs(playbook: JsonDict) -> Iterator[tuple[str, Optional[str], Optional[str], str]]:
    for task_id, node in (playbook.get("tasks") or {}).items():
        if node.get("type") != "playbook":
            continue
        inner = node.get("task") or {}
        pid, pname = sub_playbook_reference(inner)
        label = str(inner.get("name") or pname or pid or task_id)
        yield str(task_id), pid, pname, label


def is_script_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(str(value).strip()))


def _script_name_for_id(script_id: str, script_by_id: Mapping[str, Mapping[str, Any]]) -> Optional[str]:
    item = script_by_id.get(script_id)
    if not item:
        return None
    name = item.get("name")
    return str(name) if name else None


def resolve_script_binding(
    binding: str,
    *,
    script_by_id: Mapping[str, Mapping[str, Any]] | None = None,
    name_hint: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    """Resolve UUID script bindings to friendly names.

    Returns ``(display_label, raw_for_tooltip)``. ``raw_for_tooltip`` is set when
    the display differs from the stored binding (typically a script UUID).
    """
    text = str(binding or "").strip()
    if not text:
        return name_hint or "", None

    lookup = script_by_id or {}

    def resolve_id(script_id: str) -> str:
        return _script_name_for_id(script_id, lookup) or name_hint or script_id

    if is_script_uuid(text):
        display = resolve_id(text)
        return display, text if display != text else text

    if "|||" in text:
        brand, command = text.split("|||", 1)
        brand = brand.strip()
        if is_script_uuid(brand):
            resolved_brand = resolve_id(brand)
            display = f"{resolved_brand}|||{command}" if command else resolved_brand
            return display, text if display != text else None
        return text, None

    return text, None


def script_label(
    node: JsonDict,
    *,
    script_by_id: Mapping[str, Mapping[str, Any]] | None = None,
    script_by_name: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    if script_by_id is not None:
        from .entity_resolution import resolve_automation_script

        automation = resolve_automation_script(
            node,
            script_by_id=script_by_id,
            script_by_name=script_by_name or {},
        )
        if automation:
            command_info = command_display_from_task(node, script_by_id=script_by_id)
            if command_info and "|||" in str(command_info.get("command") or ""):
                return str(command_info["command"])
            return automation.command_display
        command_info = command_display_from_task(node, script_by_id=script_by_id)
        if command_info:
            return command_info["command"]

    inner = node.get("task") or {}
    hint = script_name_from_task(node)
    for raw in (
        inner.get("script"),
        inner.get("scriptName"),
        task_field(inner, "scriptId"),
    ):
        if not raw:
            continue
        display, _tooltip = resolve_script_binding(
            str(raw),
            script_by_id=script_by_id,
            name_hint=hint,
        )
        if display:
            return display
    if node.get("type") == "playbook":
        _, pname = sub_playbook_reference(inner)
        return pname or str(inner.get("name") or "")
    return ""


def script_name_from_task(node: JsonDict) -> Optional[str]:
    inner = node.get("task") or {}
    value = inner.get("scriptName")
    if value is None:
        value = task_field(inner, "scriptName")
    return str(value) if value else None


def command_binding_from_task(node: JsonDict) -> Optional[str]:
    if str(node.get("type") or "") != "regular":
        return None
    inner = node.get("task") or {}
    for raw in (inner.get("script"), task_field(inner, "scriptId"), inner.get("scriptName")):
        if raw:
            return str(raw)
    return None


def command_from_task(node: JsonDict) -> Optional[str]:
    return command_binding_from_task(node)


def command_display_from_task(
    node: JsonDict,
    *,
    script_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> Optional[dict[str, Any]]:
    """Return resolved command display metadata for a regular task."""
    binding = command_binding_from_task(node)
    if not binding:
        return None
    hint = script_name_from_task(node)
    display, raw = resolve_script_binding(binding, script_by_id=script_by_id, name_hint=hint)
    had_uuid = is_script_uuid(binding) or (
        "|||" in binding and is_script_uuid(binding.split("|||", 1)[0].strip())
    )
    resolved = had_uuid and not is_script_uuid(display)
    tooltip = raw if raw and raw != display else None
    return {
        "command": display,
        "raw": tooltip,
        "resolved": resolved,
    }


def inner_task(node: JsonDict) -> JsonDict:
    return dict(node.get("task") or {})


def resolve_start_task_id(playbook: JsonDict) -> str:
    start = str(playbook.get("startTaskId") or playbook.get("starttaskid") or "")
    tasks = playbook.get("tasks") or {}
    if start and start in tasks:
        return start
    for task_id, node in tasks.items():
        if node.get("type") == "start":
            return str(task_id)
    return start or (next(iter(tasks), "") if tasks else "")


def next_task_ids(node: JsonDict) -> tuple[str, ...]:
    successors: list[str] = []
    for targets in (node.get("nextTasks") or node.get("nexttasks") or {}).values():
        if isinstance(targets, list):
            successors.extend(str(target_id) for target_id in targets)
    return tuple(successors)


def playbook_key(playbook: JsonDict) -> str:
    pb_id, pb_name = playbook_identity(playbook)
    return pb_id or pb_name


def set_canonical(inner: JsonDict, field: str, value: str) -> None:
    keys = _KEY_ALIASES.get(field, (field,))
    for key in keys:
        inner.pop(key, None)
    inner[keys[0]] = value
