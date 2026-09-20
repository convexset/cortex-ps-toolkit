"""Normalize tenant content documents and diff copies (copy-fidelity probes)."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, MutableMapping, Sequence

ContentKind = Literal["script", "playbook", "list"]

# Server-owned / identity fields excluded when comparing a source item to a renamed copy.
COMMON_IGNORE_KEYS: frozenset[str] = frozenset({
    "id",
    "version",
    "cacheVersn",
    "cacheversn",
    "modified",
    "created",
    "definitionId",
    "definitionid",
    "itemVersion",
    "itemversion",
    "prevName",
    "prevname",
    "sequenceNumber",
    "sequencenumber",
    "primaryTerm",
    "primaryterm",
    "syncHash",
    "synchash",
    "numericId",
    "numericid",
    "indexName",
    "indexname",
    "sortValues",
    "sortvalues",
    "highlight",
    "sizeInBytes",
    "sizeinbytes",
    "MainEngineInfo",
    "commitMessage",
    "commitmessage",
    "shouldCommit",
    "shouldPublish",
    "packID",
    "packName",
    "fromServerVersion",
    "fromversion",
    "toServerVersion",
    "toversion",
    "propagationLabels",
    "user",
    "name",
})

SCRIPT_METADATA_IGNORE_KEYS: frozenset[str] = frozenset({
    "adopted",
    "commonfields",
    "contentitemexportablefields",
    "contextKeys",
    "contextkeys",
    "deprecated",
    "detached",
    "engine",
    "engineGroup",
    "enginegroup",
    "engineinfo",
    "important",
    "isInternal",
    "isinternal",
    "isOverridable",
    "isoverridable",
    "locked",
    "mainengineinfo",
    "packPropagationLabels",
    "packpropagationlabels",
    "permitted",
    "pswdProtected",
    "pswdprotected",
    "rawTags",
    "rawtags",
    "restrictioncenter",
    "runAs",
    "runas",
    "runOnce",
    "runonce",
    "sensitive",
    "signature",
    "subtype",
    "system",
    "vcShouldIgnore",
    "vcshouldignore",
    "vcShouldKeepItemLegacyProdMachine",
    "vcshouldkeepitemlegacyprodmachine",
    "visualScript",
    "visualscript",
})

SCRIPT_ARG_IGNORE_KEYS: frozenset[str] = frozenset({
    "default",
    "deprecated",
    "description",
    "hidden",
    "required",
    "secret",
    "supportedModules",
    "supportedmodules",
    "type",
})

SCRIPT_IGNORE_KEYS = COMMON_IGNORE_KEYS | SCRIPT_METADATA_IGNORE_KEYS | frozenset({
    "pswd",
    "searchableName",
    "searchablename",
    "timeout",
    "outputs",
    "comment",
})

PLAYBOOK_ENVELOPE_IGNORE_KEYS: frozenset[str] = frozenset({
    "adopted",
    "contentitemexportablefields",
    "isOverridable",
    "isoverridable",
    "outlinetasks",
    "possibleresponses",
    "packPropagationLabels",
    "packpropagationlabels",
})

PLAYBOOK_TASK_ENVELOPE_IGNORE_KEYS: frozenset[str] = frozenset({
    "continueOnErrorType",
    "continueonerrortype",
    "evidenceData",
    "evidencedata",
    "ignoreworker",
    "isautoswitchedtoquietmode",
    "isoversize",
    "note",
    "quietmode",
    "scriptArguments",
    "scriptarguments",
    "separatecontext",
    "skipunavailable",
    "timertriggers",
})

PLAYBOOK_TASK_INNER_IGNORE_KEYS: frozenset[str] = frozenset({
    "brand",
    "isCommand",
    "iscommand",
    "playbooktaskmissingcomponent",
    "istaskmissingcomponenterrordismissed",
    "script",
    "scriptId",
    "scriptid",
})

PLAYBOOK_IGNORE_KEYS = COMMON_IGNORE_KEYS | PLAYBOOK_ENVELOPE_IGNORE_KEYS | frozenset({
    "dirtyInputs",
    "dirtyinputs",
    "sourcePlaybookID",
    "sourceplaybookid",
    "taskId",
    "taskid",
    "taskIds",
    "taskids",
    "scriptIds",
    "scriptids",
    "missingScriptsIds",
    "missingscriptids",
    "brands",
    "commands",
    "nameRaw",
    "nameraw",
    "comment",
    "description",
    "view",
})

LIST_IGNORE_KEYS = COMMON_IGNORE_KEYS | frozenset({
    "truncated",
    "allRead",
    "allReadWrite",
    "system",
    "packPropagationLabels",
    "packpropagationlabels",
    "previousAllRead",
    "previousallread",
    "previousAllReadWrite",
    "previousallreadwrite",
    "OWNER",
})


def _ignore_keys(kind: ContentKind) -> frozenset[str]:
    if kind == "script":
        return SCRIPT_IGNORE_KEYS
    if kind == "playbook":
        return PLAYBOOK_IGNORE_KEYS
    return LIST_IGNORE_KEYS


def _canonical_key(key: str) -> str:
    lowered = key.lower()
    aliases = {
        "dockerimage": "dockerImage",
        "scripttarget": "scriptTarget",
        "contextkeys": "contextKeys",
        "iscommand": "isCommand",
        "scriptid": "scriptId",
        "playbookid": "playbookId",
        "playbookname": "playbookName",
        "scriptname": "scriptName",
        "taskid": "taskId",
        "nexttasks": "nextTasks",
        "starttaskid": "startTaskId",
        "scriptarguments": "scriptArguments",
        "continueonerrortype": "continueOnErrorType",
    }
    return aliases.get(lowered, key)


def _drop_ignored(node: Any, *, ignore: frozenset[str]) -> Any:
    if isinstance(node, list):
        return [_drop_ignored(item, ignore=ignore) for item in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for raw_key, value in node.items():
        key = str(raw_key)
        if key.startswith("_") or key in ignore or key.lower() in ignore:
            continue
        canon = _canonical_key(key)
        if canon in ignore or canon.lower() in ignore:
            continue
        out[canon] = _drop_ignored(value, ignore=ignore)
    return out


def _looks_like_uuid(value: str) -> bool:
    text = value.strip()
    if len(text) != 36 or text.count("-") != 4:
        return False
    return all(part.isalnum() for part in text.split("-"))


def _normalize_empty_values(node: Any) -> Any:
    if isinstance(node, dict):
        return {key: _normalize_empty_values(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_normalize_empty_values(item) for item in node]
    if node == "":
        return None
    return node


def _normalize_script_args(args: Any) -> Any:
    if not isinstance(args, list):
        return args
    cleaned: list[Any] = []
    for arg in args:
        if not isinstance(arg, dict):
            cleaned.append(arg)
            continue
        row = {
            str(key): value
            for key, value in arg.items()
            if str(key) not in SCRIPT_ARG_IGNORE_KEYS and str(key).lower() not in SCRIPT_ARG_IGNORE_KEYS
        }
        if row:
            cleaned.append(row)
    return cleaned


def _strip_task_inner(inner: dict[str, Any]) -> None:
    for key in list(inner.keys()):
        canon = _canonical_key(str(key))
        if canon in PLAYBOOK_TASK_INNER_IGNORE_KEYS or str(key).lower() in PLAYBOOK_TASK_INNER_IGNORE_KEYS:
            inner.pop(key, None)
    script_name = inner.get("scriptName") or inner.get("scriptname")
    if script_name:
        inner.pop("scriptId", None)
        inner.pop("scriptid", None)


def _normalize_playbook_task_node(node: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(node)
    for key in list(out.keys()):
        canon = _canonical_key(str(key))
        if canon in PLAYBOOK_TASK_ENVELOPE_IGNORE_KEYS or str(key).lower() in PLAYBOOK_TASK_ENVELOPE_IGNORE_KEYS:
            out.pop(key, None)
    inner = out.get("task")
    if isinstance(inner, dict):
        _strip_task_inner(inner)
    return out


def _normalize_playbook_subplaybook_refs(cleaned: dict[str, Any]) -> None:
    tasks = cleaned.get("tasks")
    if not isinstance(tasks, dict):
        return
    normalized_tasks: dict[str, Any] = {}
    for task_id, node in tasks.items():
        if isinstance(node, dict):
            normalized_tasks[str(task_id)] = _normalize_playbook_task_node(node)
        else:
            normalized_tasks[str(task_id)] = node
    cleaned["tasks"] = normalized_tasks
    for node in normalized_tasks.values():
        if not isinstance(node, dict):
            continue
        inner = node.get("task")
        if not isinstance(inner, dict):
            continue
        pname = inner.get("playbookName") or inner.get("playbookname")
        pid = inner.get("playbookId") or inner.get("playbookid")
        if pname:
            inner["playbookName"] = str(pname)
        elif pid and not _looks_like_uuid(str(pid)):
            inner["playbookName"] = str(pid)
        inner.pop("playbookId", None)
        inner.pop("playbookid", None)


def _normalize_field_mapping_items(node: Any) -> Any:
    if isinstance(node, list):
        return [_normalize_field_mapping_items(item) for item in node]
    if not isinstance(node, dict):
        return node
    out = {str(k): _normalize_field_mapping_items(v) for k, v in node.items()}
    if "fieldId" in out and "incidentfield" not in out:
        out["incidentfield"] = out.pop("fieldId")
    if "fieldid" in out and "incidentfield" not in out:
        out["incidentfield"] = out.pop("fieldid")
    return out


def normalize_representation(document: Mapping[str, Any], kind: ContentKind) -> dict[str, Any]:
    """Return a comparable view of a loaded script/playbook/list document."""
    cleaned = _drop_ignored(copy.deepcopy(dict(document)), ignore=_ignore_keys(kind))
    cleaned = _normalize_empty_values(cleaned)
    if kind == "script":
        docker = cleaned.pop("dockerImage", None) or cleaned.pop("dockerimage", None)
        if docker:
            cleaned["dockerImage"] = str(docker)
        args = cleaned.pop("arguments", None) or cleaned.pop("args", None)
        if args is not None:
            cleaned["args"] = _normalize_script_args(args)
    if kind == "list":
        data = cleaned.get("data")
        if isinstance(data, list):
            cleaned["data"] = "\n".join(str(item) for item in data)
    if kind == "playbook":
        _normalize_playbook_subplaybook_refs(cleaned)
        cleaned = _normalize_field_mapping_items(cleaned)
    return cleaned


@dataclass
class RepresentationDiff:
    kind: ContentKind
    equal: bool
    differences: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "equal": self.equal,
            "differences": self.differences,
        }


def _diff_values(path: str, left: Any, right: Any, out: list[dict[str, Any]]) -> None:
    if type(left) is not type(right):
        out.append({"path": path, "source": left, "copy": right})
        return
    if isinstance(left, dict):
        keys = sorted(set(left.keys()) | set(right.keys()))
        for key in keys:
            child = f"{path}.{key}" if path else key
            if key not in left:
                out.append({"path": child, "source": None, "copy": right[key]})
            elif key not in right:
                out.append({"path": child, "source": left[key], "copy": None})
            else:
                _diff_values(child, left[key], right[key], out)
        return
    if isinstance(left, list):
        if len(left) != len(right):
            out.append({"path": path, "source_len": len(left), "copy_len": len(right)})
        for index, (l_item, r_item) in enumerate(zip(left, right)):
            _diff_values(f"{path}[{index}]", l_item, r_item, out)
        return
    if left != right:
        out.append({"path": path, "source": left, "copy": right})


def diff_representations(
    source: Mapping[str, Any],
    copied: Mapping[str, Any],
    kind: ContentKind,
) -> RepresentationDiff:
    left = normalize_representation(source, kind)
    right = normalize_representation(copied, kind)
    differences: list[dict[str, Any]] = []
    _diff_values("", left, right, differences)
    return RepresentationDiff(kind=kind, equal=not differences, differences=differences)
