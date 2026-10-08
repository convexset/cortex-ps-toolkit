"""Playbook YAML suitable for manual import (e.g. XSOAR 6 /playbook/save/yaml)."""

from __future__ import annotations

import copy
from typing import Any, MutableMapping

from ..content.content_item_export import content_item_export_block, merge_export_document
from ..content.yaml_codec import dumps_yaml
from ..credentials import CredentialProfile
from ..portable_export_fields import drop_keys_case_insensitive, load_portable_export_policy
from . import api
from .upload_prep import prepare_playbook_for_portable_export
from .yaml_bindings import finalize_subplaybook_fields_for_yaml, prepare_playbook_bindings_for_upload
from .yaml_export import rename_playbook_keys_for_yaml


def _strip_empty_evidence(node: MutableMapping[str, Any]) -> None:
    evidence = node.get("evidencedata")
    if evidence == {} or evidence is None:
        node.pop("evidencedata", None)
        node.pop("evidenceData", None)


def _ensure_playbook_task_defaults(node: MutableMapping[str, Any]) -> None:
    """Task-node fields present on pack / tenant UI playbook exports."""
    defaults: dict[str, Any] = {
        "separatecontext": False,
        "continueonerrortype": "",
        "note": False,
        "timertriggers": [],
        "ignoreworker": False,
        "skipunavailable": False,
        "quietmode": 0,
        "isoversize": False,
        "isautoswitchedtoquietmode": False,
    }
    for key, value in defaults.items():
        if key not in node and key.lower() not in {str(k).lower() for k in node}:
            node[key] = value


def _strip_portable_metadata(playbook: MutableMapping[str, Any]) -> None:
    policy = load_portable_export_policy().playbooks
    drop_keys_case_insensitive(playbook, policy.effective_exclude_top_level())
    tasks = playbook.get("tasks")
    if not isinstance(tasks, dict):
        return
    inner_drop = policy.effective_exclude_inner_task()
    for node in tasks.values():
        if not isinstance(node, dict):
            continue
        _strip_empty_evidence(node)
        inner = node.get("task")
        if isinstance(inner, dict):
            drop_keys_case_insensitive(inner, inner_drop)
            if inner.get("scriptName") and not inner.get("iscommand") and inner.get("isCommand") is None:
                inner["iscommand"] = False
            if "brand" not in inner:
                inner["brand"] = ""


def _finalize_portable_playbook_yaml(playbook: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    yaml_ready = rename_playbook_keys_for_yaml(playbook)
    tasks = yaml_ready.get("tasks")
    if isinstance(tasks, dict):
        for node in tasks.values():
            if isinstance(node, dict):
                _ensure_playbook_task_defaults(node)
    return yaml_ready


def build_portable_playbook_yaml(profile: CredentialProfile, playbook_id: str) -> str:
    """Build YAML for offline import (XSOAR 6 UI or ``/playbook/save/yaml``).

    Uses the same shaping as tenant copy upload: ``version: -1``, JSON-string
    ``view`` fields, script/sub-playbook name bindings (no tenant UUIDs in tasks),
    and stripped Elasticsearch metadata.
    """
    source = copy.deepcopy(api.get_playbook(profile, playbook_id))
    pack_block = content_item_export_block(source)
    prepared = prepare_playbook_for_portable_export(source)
    prepare_playbook_bindings_for_upload(prepared, profile, source_profile=profile)
    finalize_subplaybook_fields_for_yaml(prepared, bind_subplaybooks_by_id=False)
    _strip_portable_metadata(prepared)
    name = str(prepared.get("name") or playbook_id)
    prepared["id"] = name
    prepared["vcShouldKeepItemLegacyProdMachine"] = bool(
        source.get("vcShouldKeepItemLegacyProdMachine", False),
    )
    body = merge_export_document(pack_block, prepared)
    return dumps_yaml(_finalize_portable_playbook_yaml(body))
