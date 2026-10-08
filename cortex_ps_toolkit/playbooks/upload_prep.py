"""Prepare playbook JSON for /playbook/save/yaml (new copy vs in-place overwrite)."""

from __future__ import annotations

import copy
import json
from typing import Any, Mapping, MutableMapping

from ..portable_export_fields import load_portable_export_policy


def _drop_private_keys(node: MutableMapping[str, Any]) -> None:
    for key in list(node.keys()):
        if str(key).startswith("_"):
            del node[key]


def _encode_view(value: Any) -> Any:
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, indent=4)


def _rewrite_field_mapping_for_yaml(node: MutableMapping[str, Any]) -> None:
    mapping = node.get("fieldMapping")
    if mapping is None:
        mapping = node.get("fieldmapping")
    if not isinstance(mapping, list):
        return
    renames = load_portable_export_policy().playbooks.effective_task_field_mapping_item_renames()
    for item in mapping:
        if not isinstance(item, dict):
            continue
        for src_key, dest_key in renames.items():
            if src_key not in item and src_key.lower() not in {str(k).lower() for k in item}:
                continue
            value = item.pop(src_key, None)
            if value is None:
                for k in list(item.keys()):
                    if str(k).lower() == src_key.lower():
                        value = item.pop(k)
                        break
            if value is not None and dest_key not in item:
                item[dest_key] = value


def _rewrite_playbook_field_mappings(playbook: MutableMapping[str, Any]) -> None:
    tasks = playbook.get("tasks")
    if not isinstance(tasks, dict):
        return
    for node in tasks.values():
        if isinstance(node, dict):
            _rewrite_field_mapping_for_yaml(node)


def _encode_playbook_views(playbook: MutableMapping[str, Any]) -> None:
    if "view" in playbook:
        playbook["view"] = _encode_view(playbook["view"])
    tasks = playbook.get("tasks")
    if not isinstance(tasks, dict):
        return
    for node in tasks.values():
        if isinstance(node, dict) and "view" in node:
            node["view"] = _encode_view(node["view"])


def prepare_playbook_for_save(
    playbook: Mapping[str, Any],
    *,
    target_playbook_id: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Shape playbook JSON for tenant YAML upload.

    For **overwrite**, the target tenant playbook id must be supplied so
    ``/playbook/save/yaml`` updates the existing playbook instead of creating
    a duplicate (or leaving the old revision in place).
    """
    pb = copy.deepcopy(dict(playbook))
    _drop_private_keys(pb)
    _encode_playbook_views(pb)
    _rewrite_playbook_field_mappings(pb)

    if overwrite:
        if not target_playbook_id:
            raise ValueError("target_playbook_id is required when overwrite=True")
        pb["id"] = target_playbook_id
    else:
        pb.pop("id", None)

    pb["version"] = -1

    tasks = pb.get("tasks")
    if not isinstance(tasks, dict):
        return pb

    for node in tasks.values():
        if not isinstance(node, dict):
            continue
        _drop_private_keys(node)
        if not overwrite:
            node.pop("taskId", None)
        inner = node.get("task")
        if isinstance(inner, dict):
            _drop_private_keys(inner)
            inner["version"] = -1
            if not overwrite:
                inner.pop("id", None)
            node["task"] = inner

    return pb


def prepare_playbook_for_portable_export(playbook: Mapping[str, Any]) -> dict[str, Any]:
    """Shape playbook JSON for offline / bundle YAML (pack-style tenant export).

    Like a new copy, but keeps canvas ``taskId`` and inner task ``id`` values,
    preserves ``description`` / ``inputs`` / ``outputs``, and sets ``version: -1``.
    """
    pb = copy.deepcopy(dict(playbook))
    _drop_private_keys(pb)
    _encode_playbook_views(pb)
    _rewrite_playbook_field_mappings(pb)

    comment = pb.get("comment")
    if comment and not pb.get("description"):
        pb["description"] = str(comment)

    pb["version"] = -1
    pb.pop("id", None)

    tasks = pb.get("tasks")
    if not isinstance(tasks, dict):
        return pb

    for node in tasks.values():
        if not isinstance(node, dict):
            continue
        _drop_private_keys(node)
        inner = node.get("task")
        if isinstance(inner, dict):
            _drop_private_keys(inner)
            inner["version"] = -1
            node["task"] = inner

    return pb
