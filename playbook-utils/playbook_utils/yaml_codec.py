"""Turn API playbook JSON into YAML accepted by /playbook/save/yaml."""

from __future__ import annotations

import json
from typing import Any, List, Mapping, MutableMapping, Optional
from uuid import uuid4

import yaml

from .fields import FieldPolicy, drop_keys
from .keys import (
    JsonDict,
    get_field,
    inner_task,
    normalize_playbook,
    pop_field,
    rename_known_keys_to_yaml,
    set_canonical,
)


def _str_presenter(dumper: yaml.Dumper, data: str) -> yaml.Node:
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


class _PlaybookDumper(yaml.SafeDumper):
    pass


_PlaybookDumper.add_representer(str, _str_presenter)


def encode_view(view: Any) -> Any:
    if view is None:
        return None
    if isinstance(view, str):
        return view
    return json.dumps(view, indent=4)


def rewrite_inner_task_for_yaml(
    inner: JsonDict,
    *,
    script_names: Optional[Mapping[str, str]] = None,
    playbook_names: Optional[Mapping[str, str]] = None,
    bind_subplaybooks_by_id: bool = False,
) -> None:
    """API JSON uses scriptId/playbookId; YAML save needs scriptName/script/playbookName.

    `/playbook/save/yaml` ignores `scriptid`. Regular automations bind via `scriptName`;
    integration commands bind via `script` (`Brand|||command`). Sub-playbook calls bind
    via `playbookName` on XSOAR, or via tenant `playbookId` on XSIAM when
    ``bind_subplaybooks_by_id`` is set. Same-tenant copies still do this conversion
    (it is not an id remap across tenants).
    """
    script_id = get_field(inner, "scriptId")
    if isinstance(script_id, str) and script_id:
        is_command = bool(get_field(inner, "isCommand")) or "|||" in script_id
        if is_command:
            inner["script"] = script_id
            pop_field(inner, "scriptId")
            set_canonical(inner, "isCommand", True)
        else:
            name = get_field(inner, "scriptName")
            if not name:
                if script_names and script_id in script_names:
                    name = script_names[script_id]
                else:
                    name = script_id
            set_canonical(inner, "scriptName", str(name))
            pop_field(inner, "scriptId")
            if get_field(inner, "isCommand") is None:
                set_canonical(inner, "isCommand", False)

    playbook_id = get_field(inner, "playbookId")
    if playbook_id:
        name = get_field(inner, "playbookName")
        if not name and playbook_names and str(playbook_id) in playbook_names:
            name = playbook_names[str(playbook_id)]
        if bind_subplaybooks_by_id:
            set_canonical(inner, "playbookId", str(playbook_id))
            # XSIAM YAML exports bind via playbookName when the canvas task title
            # (inner.name) differs from the sub-playbook name. Keep both fields.
            if name:
                set_canonical(inner, "playbookName", str(name))
        else:
            if not name:
                name = str(playbook_id)
            set_canonical(inner, "playbookName", str(name))
            pop_field(inner, "playbookId")


def rewrite_field_mapping_for_yaml(node: MutableMapping[str, Any]) -> None:
    """API JSON uses fieldId; tenant YAML exports use incidentfield."""
    mapping = node.get("fieldMapping")
    if mapping is None:
        mapping = node.get("fieldmapping")
    if not isinstance(mapping, list):
        return
    for item in mapping:
        if not isinstance(item, dict):
            continue
        field_id = pop_field(item, "fieldId")
        if field_id is not None and "incidentfield" not in item:
            item["incidentfield"] = field_id


def prepare_for_upload(
    playbook: Mapping[str, Any],
    *,
    policy: Optional[FieldPolicy] = None,
    new_id: Optional[str] = None,
    new_name: Optional[str] = None,
    source_playbook_id: Optional[str] = None,
    script_names: Optional[Mapping[str, str]] = None,
    playbook_names: Optional[Mapping[str, str]] = None,
    bind_subplaybooks_by_id: bool = False,
    preserve_task_identifiers: bool = False,
) -> JsonDict:
    """Drop server metadata, force version -1, stringify views, YAML-safe key names."""
    policy = policy or FieldPolicy()
    pb = normalize_playbook(playbook)
    drop_keys(pb, policy.drop_playbook_keys)
    for key in list(pb.keys()):
        if str(key).startswith("_"):
            del pb[key]

    if new_name is not None:
        pb["name"] = new_name
    if new_id is not None:
        pb["id"] = new_id
    pb["version"] = -1
    if source_playbook_id:
        pb["sourcePlaybookID"] = source_playbook_id
    elif "sourcePlaybookID" not in pb and playbook.get("id"):
        pb["sourcePlaybookID"] = playbook.get("id")

    comment = pb.get("comment")
    if comment and "description" not in pb:
        pb["description"] = str(comment)
        del pb["comment"]

    tasks = pb.get("tasks") or {}
    for _tid, node in list(tasks.items()):
        if not isinstance(node, dict):
            continue
        drop_keys(node, policy.drop_task_node_keys)
        if not preserve_task_identifiers:
            pop_field(node, "taskId")
        inner = inner_task(node)
        if inner:
            drop_keys(inner, policy.drop_inner_task_keys)
            inner["version"] = -1
            if "brand" not in inner:
                inner["brand"] = ""
            rewrite_inner_task_for_yaml(
                inner,
                script_names=script_names,
                playbook_names=playbook_names,
                bind_subplaybooks_by_id=bind_subplaybooks_by_id,
            )
            node["task"] = inner
            if not inner:
                del node["task"]
        if "view" in node:
            node["view"] = encode_view(node["view"])
        rewrite_field_mapping_for_yaml(node)

    if "view" in pb:
        pb["view"] = encode_view(pb["view"])

    return rename_known_keys_to_yaml(pb)


def prepare_for_overwrite(
    playbook: Mapping[str, Any],
    *,
    policy: Optional[FieldPolicy] = None,
    script_names: Optional[Mapping[str, str]] = None,
    playbook_names: Optional[Mapping[str, str]] = None,
    bind_subplaybooks_by_id: bool = False,
) -> JsonDict:
    """Prepare an in-place playbook update, preserving playbook and task identifiers."""
    pb = normalize_playbook(playbook)
    playbook_id = str(pb.get("id") or "")
    overwrite_policy = policy or FieldPolicy(
        drop_inner_task_keys=tuple(
            key for key in FieldPolicy().drop_inner_task_keys if key != "id"
        ),
        drop_task_node_keys=(),
    )
    return prepare_for_upload(
        pb,
        policy=overwrite_policy,
        new_id=playbook_id or None,
        source_playbook_id=playbook_id or None,
        script_names=script_names,
        playbook_names=playbook_names,
        bind_subplaybooks_by_id=bind_subplaybooks_by_id,
        preserve_task_identifiers=True,
    )


def dumps_yaml(
    playbook: Mapping[str, Any],
    *,
    policy: Optional[FieldPolicy] = None,
    script_names: Optional[Mapping[str, str]] = None,
    playbook_names: Optional[Mapping[str, str]] = None,
    bind_subplaybooks_by_id: bool = False,
    preserve_task_identifiers: bool = False,
    overwrite: bool = False,
) -> str:
    if overwrite:
        prepared = prepare_for_overwrite(
            playbook,
            policy=policy,
            script_names=script_names,
            playbook_names=playbook_names,
            bind_subplaybooks_by_id=bind_subplaybooks_by_id,
        )
    else:
        prepared = prepare_for_upload(
            playbook,
            policy=policy,
            script_names=script_names,
            playbook_names=playbook_names,
            bind_subplaybooks_by_id=bind_subplaybooks_by_id,
            preserve_task_identifiers=preserve_task_identifiers,
        )
    return yaml.dump(
        prepared,
        Dumper=_PlaybookDumper,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )


def new_uuid() -> str:
    return str(uuid4())
