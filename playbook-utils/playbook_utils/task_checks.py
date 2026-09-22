"""Validate playbook task node types before applying task-level updates."""

from __future__ import annotations

from typing import Mapping

from .keys import get_field, inner_task, task_name, task_type


def has_script_binding(node: Mapping[str, object]) -> bool:
    """True when the inner task binds an automation script or integration command."""
    inner = inner_task(node)
    if get_field(inner, "scriptId"):
        return True
    if get_field(inner, "scriptName"):
        return True
    if get_field(inner, "script"):
        return True
    return False


def check_regular_script_task(node: Mapping[str, object], task_id: str) -> None:
    """Require a regular task with a script/command binding."""
    node_type = task_type(node)
    if node_type != "regular":
        raise ValueError(
            f"task {task_id} ({task_name(node)!r}): retry/error-handling updates require "
            f"type 'regular' with a script, got type {node_type!r}"
        )
    if not has_script_binding(node):
        raise ValueError(
            f"task {task_id} ({task_name(node)!r}): regular task has no script binding "
            "(expected scriptId, scriptName, or script on inner task)"
        )


def check_playbook_task(node: Mapping[str, object], task_id: str) -> None:
    """Require a sub-playbook call task."""
    node_type = task_type(node)
    if node_type != "playbook":
        raise ValueError(
            f"task {task_id} ({task_name(node)!r}): context-sharing updates require "
            f"type 'playbook', got type {node_type!r}"
        )
    inner = inner_task(node)
    if not (get_field(inner, "playbookId") or get_field(inner, "playbookName")):
        raise ValueError(
            f"task {task_id} ({task_name(node)!r}): playbook task has no sub-playbook binding"
        )
