"""Rename playbook API JSON keys to YAML spellings accepted by /playbook/save/yaml."""

from __future__ import annotations

from typing import Any

# Subset aligned with bay/playbook-utils/playbook_utils/keys.py (CANONICAL_TO_YAML).
_CANONICAL_TO_YAML: dict[str, str] = {
    "startTaskId": "starttaskid",
    "taskId": "taskid",
    "nextTasks": "nexttasks",
    "scriptArguments": "scriptarguments",
    "keyValue": "keyvalue",
    "separateContext": "separatecontext",
    "continueOnError": "continueonerror",
    "continueOnErrorType": "continueonerrortype",
    "timerTriggers": "timertriggers",
    "ignoreWorker": "ignoreworker",
    "skipUnavailable": "skipunavailable",
    "quietMode": "quietmode",
    "isOverSize": "isoversize",
    "isAutoSwitchedToQuietMode": "isautoswitchedtoquietmode",
    "isCommand": "iscommand",
    "ignoreCase": "ignorecase",
    "isContext": "iscontext",
    "playbookId": "playbookid",
    "scriptId": "scriptid",
    "sourcePlaybookID": "sourceplaybookid",
    "nameRaw": "nameraw",
    "taskIds": "taskids",
    "scriptIds": "scriptids",
    "missingScriptsIds": "missingscriptids",
    "cacheVersn": "cacheversn",
    "sizeInBytes": "sizeinbytes",
    "fieldMapping": "fieldmapping",
    "evidenceData": "evidencedata",
    "reputationCalc": "reputationcalc",
    "restrictedCompletion": "restrictedcompletion",
    "defaultAssigneeComplex": "defaultassigneecomplex",
    "externalFormUseAuth": "externalformuseauth",
    "formDisplay": "formdisplay",
    "slaReminder": "slareminder",
    "fieldName": "fieldname",
    "labelArg": "labelarg",
    "optionsArg": "optionsarg",
    "retriesCount": "retriescount",
    "retriesInterval": "retriesinterval",
    "completeAfterReplies": "completeafterreplies",
    "completeAfterV2": "completeafterv2",
    "completeAfterSla": "completeaftersla",
    "readOnly": "readonly",
    "gridColumns": "gridcolumns",
    "defaultRows": "defaultrows",
    "fieldAssociated": "fieldassociated",
    "isTitleTask": "istitletask",
}

_YAML_PRESERVE_CASE = frozenset({
    "scriptName",
    "playbookName",
    "exitCondition",
    "inputSections",
    "fieldMapping",
})


def yaml_name_for_key(key: str) -> str:
    source = str(key)
    if source in _YAML_PRESERVE_CASE:
        return source
    for preserved in _YAML_PRESERVE_CASE:
        if preserved.lower() == source.lower():
            return preserved
    return _CANONICAL_TO_YAML.get(source, source)


def rename_playbook_keys_for_yaml(obj: Any) -> Any:
    """Recursively rename keys to spellings ``/playbook/save/yaml`` accepts."""
    if isinstance(obj, list):
        return [rename_playbook_keys_for_yaml(item) for item in obj]
    if not isinstance(obj, dict):
        return obj
    renamed: dict[str, Any] = {}
    for key, value in obj.items():
        yaml_key = yaml_name_for_key(str(key))
        if yaml_key in renamed and yaml_key != str(key):
            continue
        renamed[yaml_key] = rename_playbook_keys_for_yaml(value)
    return renamed
