"""API → upload YAML key remaps for playbooks and scripts (code-only)."""

from __future__ import annotations

# Playbook API camelCase → lowercase YAML (`rename_playbook_keys_for_yaml`).
# Aligned with playbook-utils/playbook_utils/keys.py CANONICAL_TO_YAML.
DEFAULT_PLAYBOOK_KEY_RENAMES: dict[str, str] = {
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

DEFAULT_PLAYBOOK_PRESERVE_KEY_CASE: tuple[str, ...] = (
    "scriptName",
    "playbookName",
    "exitCondition",
    "inputSections",
    "fieldMapping",
)

# Keys renamed inside each task ``fieldMapping[]`` item (not recursive tree renames).
DEFAULT_PLAYBOOK_TASK_FIELD_MAPPING_ITEM_RENAMES: dict[str, str] = {
    "fieldId": "incidentfield",
    "fieldid": "incidentfield",
}

# Script automation/load JSON → YAML save spellings.
DEFAULT_SCRIPT_KEY_RENAMES: dict[str, str] = {
    "dockerImage": "dockerimage",
    "scriptTarget": "scripttarget",
    "arguments": "args",
    "runAs": "runas",
    "runOnce": "runonce",
}

# Integration ModuleConfiguration → demisto-style integration YAML.
DEFAULT_INTEGRATION_CONFIG_PARAM_RENAMES: dict[str, str] = {
    "defaultValue": "defaultvalue",
    "info": "additionalinfo",
}

DEFAULT_INTEGRATION_TOP_LEVEL_RENAMES: dict[str, str] = {
    "detailedDescription": "detaileddescription",
    "restrictionCenter": "restrictioncenter",
}
