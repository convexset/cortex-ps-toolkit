"""Configurable ignore / drop / rewrite field policy.

The round-trip through the tenant will rewrite some keys. (B) uses this policy
so we can widen or narrow what equality means without changing traversal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple

from .keys import JsonDict

# Playbook-level keys dropped before YAML upload (server-owned metadata).
DEFAULT_DROP_PLAYBOOK_KEYS: Tuple[str, ...] = (
    "cacheVersn",
    "modified",
    "created",
    "sizeInBytes",
    "packID",
    "packName",
    "itemVersion",
    "fromServerVersion",
    "toServerVersion",
    "propagationLabels",
    "definitionId",
    "vcShouldIgnore",
    "vcShouldKeepItemLegacyProdMachine",
    "commitMessage",
    "shouldCommit",
    "taskIds",
    "sequenceNumber",
    "primaryTerm",
    "syncHash",
    "numericId",
    "indexName",
    "sortValues",
    "highlight",
    "isOverridable",
    "prevName",
    "missingScriptsIds",
)

# Inner task (`node["task"]`) keys dropped before YAML upload.
DEFAULT_DROP_INNER_TASK_KEYS: Tuple[str, ...] = (
    "id",
    "modified",
    "created",
    "sizeInBytes",
    "cacheVersn",
    "sequenceNumber",
    "primaryTerm",
    "numericId",
    "syncHash",
    "indexName",
    "sortValues",
    "highlight",
)

# Task-node keys dropped before YAML upload.
DEFAULT_DROP_TASK_NODE_KEYS: Tuple[str, ...] = (
    "taskId",
)

# Fields ignored by equality (A/B comparison), including ids and canvas.
DEFAULT_COMPARE_IGNORE_KEYS: Tuple[str, ...] = (
    "id",
    "taskId",
    "taskid",
    "view",
    "version",
    "cacheVersn",
    "modified",
    "created",
    "sizeInBytes",
    "sequenceNumber",
    "primaryTerm",
    "numericId",
    "syncHash",
    "indexName",
    "sortValues",
    "highlight",
    "taskIds",
    "packID",
    "packName",
    "itemVersion",
    "fromServerVersion",
    "toServerVersion",
    "propagationLabels",
    "definitionId",
    "vcShouldIgnore",
    "vcShouldKeepItemLegacyProdMachine",
    "commitMessage",
    "shouldCommit",
    "sourcePlaybookID",
    "formDisplay",
    "formdisplay",
    "nameRaw",
    "prevName",
    "missingScriptsIds",
    "commands",
    "brands",
    "scriptIds",
    "system",
    "deprecated",
    "hidden",
    "quiet",
    "roles",
    "hasRole",
    "previousRoles",
    "packPropagationLabels",
    "comment",
    "tags",
    "dirtyInputs",
    "adopted",
    "outlineTasks",
    "outlinetasks",
    "possibleresponses",
    "aclrelations",
    "aclowner",
    "_canonical_index",
    "_orig_id",
    "_orig_ids",
    # XSIAM YAML ZIP get fills these defaults; they are not subgraph logic.
    "continueOnErrorType",
    "evidenceData",
    "ignoreWorker",
    "isAutoSwitchedToQuietMode",
    "isOverSize",
    "quietMode",
    "skipUnavailable",
    "timerTriggers",
    "isTaskMissingComponentErrorDismissed",
    "playbookTaskMissingComponent",
    "isTitleTask",
    "clonedFrom",
)


def _as_tuple(values: Optional[Iterable[str]], default: Sequence[str]) -> Tuple[str, ...]:
    if values is None:
        return tuple(default)
    return tuple(str(v) for v in values)


@dataclass(frozen=True)
class FieldPolicy:
    """What to drop on upload vs ignore when comparing subgraphs."""

    drop_playbook_keys: Tuple[str, ...] = DEFAULT_DROP_PLAYBOOK_KEYS
    drop_inner_task_keys: Tuple[str, ...] = DEFAULT_DROP_INNER_TASK_KEYS
    drop_task_node_keys: Tuple[str, ...] = DEFAULT_DROP_TASK_NODE_KEYS
    compare_ignore_keys: Tuple[str, ...] = DEFAULT_COMPARE_IGNORE_KEYS

    @classmethod
    def from_mapping(cls, data: Optional[Mapping[str, Any]] = None) -> "FieldPolicy":
        if not data:
            return cls()
        return cls(
            drop_playbook_keys=_as_tuple(data.get("drop_playbook_keys"), DEFAULT_DROP_PLAYBOOK_KEYS),
            drop_inner_task_keys=_as_tuple(data.get("drop_inner_task_keys"), DEFAULT_DROP_INNER_TASK_KEYS),
            drop_task_node_keys=_as_tuple(data.get("drop_task_node_keys"), DEFAULT_DROP_TASK_NODE_KEYS),
            compare_ignore_keys=_as_tuple(data.get("compare_ignore_keys"), DEFAULT_COMPARE_IGNORE_KEYS),
        )

    def to_dict(self) -> JsonDict:
        return {
            "drop_playbook_keys": list(self.drop_playbook_keys),
            "drop_inner_task_keys": list(self.drop_inner_task_keys),
            "drop_task_node_keys": list(self.drop_task_node_keys),
            "compare_ignore_keys": list(self.compare_ignore_keys),
        }

    def ignore_set(self) -> Set[str]:
        names = set(self.compare_ignore_keys)
        names.update(n.lower() for n in self.compare_ignore_keys)
        return names


def drop_keys(obj: MutableMapping[str, Any], keys: Iterable[str]) -> List[str]:
    """Delete keys under exact or case-insensitive match. Return removed names."""
    wanted = {str(k) for k in keys}
    wanted_lower = {k.lower() for k in wanted}
    removed: List[str] = []
    for key in list(obj.keys()):
        if key in wanted or str(key).lower() in wanted_lower:
            del obj[key]
            removed.append(str(key))
    return removed


def strip_ignored(value: Any, ignore: Set[str]) -> Any:
    """Deep-copy a structure, dropping ignored keys at every dict level."""
    if isinstance(value, list):
        return [strip_ignored(item, ignore) for item in value]
    if not isinstance(value, dict):
        return value
    out: JsonDict = {}
    for key, item in value.items():
        if key in ignore or str(key).lower() in ignore:
            continue
        out[str(key)] = strip_ignored(item, ignore)
    return out


def load_policy_file(path: Optional[str]) -> FieldPolicy:
    if not path:
        return FieldPolicy()
    import json
    from pathlib import Path

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Field policy file must be a JSON object: {path}")
    return FieldPolicy.from_mapping(payload)
