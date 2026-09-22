"""Normalize playbook JSON/YAML key variants (camelCase vs lowercase)."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Iterator, List, Mapping, MutableMapping, Optional, Tuple

JsonDict = Dict[str, Any]

# Canonical (API JSON) name -> accepted aliases when reading.
_ALIASES: Dict[str, Tuple[str, ...]] = {
    "startTaskId": ("startTaskId", "starttaskid"),
    "taskId": ("taskId", "taskid"),
    "nextTasks": ("nextTasks", "nexttasks"),
    "scriptArguments": ("scriptArguments", "scriptarguments"),
    "keyValue": ("keyValue", "keyvalue"),
    "separateContext": ("separateContext", "separatecontext"),
    "continueOnError": ("continueOnError", "continueonerror"),
    "continueOnErrorType": ("continueOnErrorType", "continueonerrortype"),
    "timerTriggers": ("timerTriggers", "timertriggers"),
    "ignoreWorker": ("ignoreWorker", "ignoreworker"),
    "skipUnavailable": ("skipUnavailable", "skipunavailable"),
    "quietMode": ("quietMode", "quietmode"),
    "isOverSize": ("isOverSize", "isoversize"),
    "isAutoSwitchedToQuietMode": ("isAutoSwitchedToQuietMode", "isautoswitchedtoquietmode"),
    "isCommand": ("isCommand", "iscommand"),
    "ignoreCase": ("ignoreCase", "ignorecase"),
    "isContext": ("isContext", "iscontext"),
    "playbookId": ("playbookId", "playbookid"),
    "playbookName": ("playbookName", "playbookname"),
    "scriptId": ("scriptId", "scriptid"),
    "scriptName": ("scriptName", "scriptname"),
    "sourcePlaybookID": ("sourcePlaybookID", "sourceplaybookid"),
    "nameRaw": ("nameRaw", "nameraw"),
    "taskIds": ("taskIds", "taskids"),
    "scriptIds": ("scriptIds", "scriptids"),
    "missingScriptsIds": ("missingScriptsIds", "missingscriptsids"),
    "cacheVersn": ("cacheVersn", "cacheversn"),
    "sizeInBytes": ("sizeInBytes", "sizeinbytes"),
    "fieldMapping": ("fieldMapping", "fieldmapping"),
    "evidenceData": ("evidenceData", "evidencedata"),
    "reputationCalc": ("reputationCalc", "reputationcalc"),
    "restrictedCompletion": ("restrictedCompletion", "restrictedcompletion"),
    "defaultAssigneeComplex": ("defaultAssigneeComplex", "defaultassigneecomplex"),
    "externalFormUseAuth": ("externalFormUseAuth", "externalformuseauth"),
    "formDisplay": ("formDisplay", "formdisplay"),
    "slaReminder": ("slaReminder", "slareminder"),
    "fieldName": ("fieldName", "fieldname"),
    "labelArg": ("labelArg", "labelarg"),
    "optionsArg": ("optionsArg", "optionsarg"),
    "retriesCount": ("retriesCount", "retriescount"),
    "retriesInterval": ("retriesInterval", "retriesinterval"),
    "completeAfterReplies": ("completeAfterReplies", "completeafterreplies"),
    "completeAfterV2": ("completeAfterV2", "completeafterv2"),
    "completeAfterSla": ("completeAfterSla", "completeaftersla"),
    "readOnly": ("readOnly", "readonly"),
    "gridColumns": ("gridColumns", "gridcolumns"),
    "defaultRows": ("defaultRows", "defaultrows"),
    "fieldAssociated": ("fieldAssociated", "fieldassociated"),
    "isTitleTask": ("isTitleTask", "istitletask"),
    "isTaskMissingComponentErrorDismissed": (
        "isTaskMissingComponentErrorDismissed",
        "istaskmissingcomponenterrordismissed",
    ),
    "playbookTaskMissingComponent": (
        "playbookTaskMissingComponent",
        "playbooktaskmissingcomponent",
    ),
}

CANONICAL_KEYS: Tuple[str, ...] = tuple(_ALIASES.keys())

# Keys that tenant YAML exports keep in mixed/camelCase. All other keys in
# `_ALIASES` map to the lowercase YAML form on upload. Playbook input names
# are not rewritten. Inner-task `scriptName` / `playbookName` must stay
# camelCase or `/playbook/save/yaml` drops the binding.
YAML_PRESERVE_CASE = frozenset(
    {
        "scriptName",
        "playbookName",
        "exitCondition",
        "inputSections",
        "vcShouldKeepItemLegacyProdMachine",
        "fieldMapping",
    }
)

CANONICAL_TO_YAML: Dict[str, str] = {
    canonical: aliases[-1]
    for canonical, aliases in _ALIASES.items()
    if aliases[-1] != canonical and canonical not in YAML_PRESERVE_CASE
}


def get_field(obj: Optional[Mapping[str, Any]], field: str, default: Any = None) -> Any:
    """Read a field using canonical name or lowercase alias."""
    if not obj:
        return default
    if field in obj:
        return obj[field]
    for alias in _ALIASES.get(field, (field,)):
        if alias in obj:
            return obj[alias]
    lowered = field.lower()
    for key, value in obj.items():
        if str(key).lower() == lowered:
            return value
    return default


def pop_field(obj: MutableMapping[str, Any], field: str, default: Any = None) -> Any:
    """Remove a field under any known alias and return its value."""
    keys = []
    for alias in _ALIASES.get(field, (field,)):
        if alias in obj:
            keys.append(alias)
    lowered = field.lower()
    for key in list(obj.keys()):
        if str(key).lower() == lowered and key not in keys:
            keys.append(key)
    value = default
    for key in keys:
        value = obj.pop(key)
    return value


def set_canonical(obj: MutableMapping[str, Any], field: str, value: Any) -> None:
    """Write a canonical field name, dropping aliases."""
    pop_field(obj, field)
    obj[field] = value


def next_tasks_map(node: Mapping[str, Any]) -> Dict[str, List[str]]:
    """Return branch-label -> successor ids, coerced to strings."""
    raw = get_field(node, "nextTasks") or {}
    if not isinstance(raw, Mapping):
        return {}
    result: Dict[str, List[str]] = {}
    for label, targets in raw.items():
        if targets is None:
            result[str(label)] = []
        elif isinstance(targets, list):
            result[str(label)] = [str(t) for t in targets]
        else:
            result[str(label)] = [str(targets)]
    return result


def iter_successors(node: Mapping[str, Any]) -> Iterator[Tuple[str, str]]:
    """Yield (branch_label, target_id) in a deterministic order."""
    mapping = next_tasks_map(node)
    for label in sorted(mapping.keys()):
        for target in mapping[label]:
            yield label, target


def successor_ids(node: Mapping[str, Any]) -> Tuple[str, ...]:
    """Return successor ids in deterministic order (may contain duplicates)."""
    return tuple(target for _, target in iter_successors(node))


def parse_view(view: Any) -> Optional[JsonDict]:
    """Parse a task/playbook view that may be a dict or a JSON string."""
    if view is None:
        return None
    if isinstance(view, str):
        text = view.strip()
        if not text:
            return None
        loaded = json.loads(text)
        return loaded if isinstance(loaded, dict) else None
    if isinstance(view, Mapping):
        return dict(view)
    return None


def task_position(node: Mapping[str, Any]) -> Optional[Tuple[float, float]]:
    """Return (x, y) canvas position, or None if missing."""
    view = parse_view(node.get("view"))
    if not view:
        return None
    pos = view.get("position") or {}
    if "x" not in pos and "y" not in pos:
        return None
    return float(pos.get("x") or 0), float(pos.get("y") or 0)


def set_task_position(node: MutableMapping[str, Any], x: float, y: float) -> None:
    """Write view.position, preserving whether view was stored as a string."""
    as_string = isinstance(node.get("view"), str)
    view = parse_view(node.get("view")) or {}
    position = dict(view.get("position") or {})
    position["x"] = x
    position["y"] = y
    view["position"] = position
    if as_string:
        node["view"] = json.dumps(view, indent=4)
    else:
        node["view"] = view


def playbook_tasks(playbook: Mapping[str, Any]) -> Dict[str, JsonDict]:
    """Return tasks keyed by string id."""
    raw = playbook.get("tasks") or {}
    if not isinstance(raw, Mapping):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, Mapping)}


def inner_task(node: Mapping[str, Any]) -> JsonDict:
    inner = node.get("task")
    return inner if isinstance(inner, dict) else {}


def task_type(node: Mapping[str, Any]) -> str:
    return str(node.get("type") or inner_task(node).get("type") or "")


def task_name(node: Mapping[str, Any]) -> str:
    return str(inner_task(node).get("name") or "")


def start_task_id(playbook: Mapping[str, Any]) -> str:
    start = str(get_field(playbook, "startTaskId") or "")
    tasks = playbook_tasks(playbook)
    if start and start in tasks:
        return start
    for tid, node in tasks.items():
        if task_type(node) == "start":
            return tid
    return start


def stringify_next_tasks(node: MutableMapping[str, Any]) -> None:
    mapping = next_tasks_map(node)
    if mapping:
        set_canonical(node, "nextTasks", mapping)
    elif get_field(node, "nextTasks") is not None:
        pop_field(node, "nextTasks")


def normalize_playbook(playbook: Mapping[str, Any]) -> JsonDict:
    """Deep-copy-ish normalize: string task ids, canonical nextTasks keys."""
    pb = dict(playbook)
    tasks_in = playbook.get("tasks") or {}
    tasks: JsonDict = {}
    if isinstance(tasks_in, Mapping):
        for key, node in tasks_in.items():
            if not isinstance(node, Mapping):
                continue
            copied: JsonDict = dict(node)
            if isinstance(copied.get("task"), Mapping):
                copied["task"] = dict(copied["task"])
            stringify_next_tasks(copied)
            copied["id"] = str(copied.get("id") if copied.get("id") is not None else key)
            tasks[str(key)] = copied
    pb["tasks"] = tasks
    start = start_task_id(pb)
    if start:
        set_canonical(pb, "startTaskId", start)
    return pb


_ALIAS_LOWER_TO_CANONICAL: Dict[str, str] = {}
for _canonical, _aliases in _ALIASES.items():
    _ALIAS_LOWER_TO_CANONICAL[_canonical.lower()] = _canonical
    for _alias in _aliases:
        _ALIAS_LOWER_TO_CANONICAL[_alias.lower()] = _canonical


def canonical_name_for_key(key: str) -> str:
    """Map YAML/lowercase aliases to the API JSON camelCase name."""
    source = str(key)
    if source in YAML_PRESERVE_CASE:
        return source
    mapped = _ALIAS_LOWER_TO_CANONICAL.get(source.lower())
    return mapped or source


def rename_known_keys_to_canonical(obj: Any) -> Any:
    """Recursively rename known aliases to canonical camelCase (XSIAM YAML vs JSON)."""
    if isinstance(obj, list):
        return [rename_known_keys_to_canonical(item) for item in obj]
    if not isinstance(obj, dict):
        return obj
    renamed: JsonDict = {}
    for key, value in obj.items():
        canon = canonical_name_for_key(str(key))
        converted = rename_known_keys_to_canonical(value)
        if canon in renamed:
            if renamed[canon] is None and converted is not None:
                renamed[canon] = converted
            continue
        renamed[canon] = converted
    return renamed


def drop_none_values(obj: Any) -> Any:
    """Drop keys whose value is None so omitted YAML fields match JSON nulls."""
    if isinstance(obj, list):
        return [drop_none_values(item) for item in obj]
    if not isinstance(obj, dict):
        return obj
    return {str(key): drop_none_values(value) for key, value in obj.items() if value is not None}


def drop_compare_defaults(obj: Any) -> Any:
    """Omit empty YAML/JSON defaults (None, False, 0, '', [], {}) for equality."""
    if isinstance(obj, list):
        return [drop_compare_defaults(item) for item in obj]
    if not isinstance(obj, dict):
        return obj
    out: JsonDict = {}
    for key, value in obj.items():
        if value is None or value is False or value == 0 or value == "" or value == [] or value == {}:
            continue
        converted = drop_compare_defaults(value)
        if converted is None or converted is False or converted == 0 or converted == "" or converted == [] or converted == {}:
            continue
        out[str(key)] = converted
    return out


def align_script_fields_for_compare(inner: MutableMapping[str, Any]) -> None:
    """Treat YAML ``script: Brand|||command`` as the same binding as API ``scriptId``."""
    script = inner.get("script")
    script_id = get_field(inner, "scriptId")
    if isinstance(script, str) and script and not script_id:
        set_canonical(inner, "scriptId", script)
        script_id = script
    if script_id and inner.get("script") == script_id:
        inner.pop("script", None)
    script_id = get_field(inner, "scriptId")
    if isinstance(script_id, str) and "|||" in script_id:
        _, _, command = script_id.partition("|||")
        set_canonical(inner, "scriptId", f"|||{command}")
        inner.pop("brand", None)


def align_playbook_fields_for_compare(inner: MutableMapping[str, Any]) -> None:
    """Normalize sub-playbook bindings for compare.

    Task display titles (``inner.name``) are not playbook names. Prefer ``playbookId``,
    then explicit ``playbookName``.
    """
    if inner.get("type") == "playbook":
        playbook_id = get_field(inner, "playbookId")
        playbook_name = get_field(inner, "playbookName")
        binding = playbook_id or playbook_name
        if binding:
            set_canonical(inner, "playbookId", str(binding))
            pop_field(inner, "playbookName")
        return
    playbook_id = get_field(inner, "playbookId")
    playbook_name = get_field(inner, "playbookName")
    if playbook_name and not playbook_id:
        set_canonical(inner, "playbookId", playbook_name)
        playbook_id = playbook_name
    if playbook_id and playbook_name == playbook_id:
        pop_field(inner, "playbookName")


def yaml_name_for_key(key: str) -> str:
    """YAML spelling for an API/JSON key.

    Preserve `scriptName` / `playbookName` and mixed-case keys that tenant YAML
    exports keep (for example `exitCondition`). Known aliases map to lowercase.
    Other keys are left unchanged so playbook input/argument names are not
    rewritten.
    """
    source = str(key)
    if source in YAML_PRESERVE_CASE:
        return source
    for preserved in YAML_PRESERVE_CASE:
        if preserved.lower() == source.lower():
            return preserved
    return CANONICAL_TO_YAML.get(source, source)


def rename_known_keys_to_yaml(obj: Any) -> Any:
    """Recursively rename keys to the spellings `/playbook/save/yaml` accepts."""
    if isinstance(obj, list):
        return [rename_known_keys_to_yaml(item) for item in obj]
    if not isinstance(obj, dict):
        return obj
    renamed: JsonDict = {}
    for key, value in obj.items():
        yaml_key = yaml_name_for_key(str(key))
        if yaml_key in renamed and yaml_key != str(key):
            continue
        renamed[yaml_key] = rename_known_keys_to_yaml(value)
    return renamed
