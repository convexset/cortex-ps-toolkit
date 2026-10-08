"""Playbook and script field policy for portable YAML export (code-only).

Single source of truth for include/exclude/remap rules used by bundle export and
tenant copy YAML paths. Documented in ``docs/PORTABLE_EXPORT_FIELDS.md``.

To change behavior: edit this module and ``portable_export_remaps.py``, then update
the doc and run ``pytest tests/test_portable_export_reference.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, MutableMapping

from .portable_export_remaps import (
    DEFAULT_INTEGRATION_CONFIG_PARAM_RENAMES,
    DEFAULT_INTEGRATION_TOP_LEVEL_RENAMES,
    DEFAULT_PLAYBOOK_KEY_RENAMES,
    DEFAULT_PLAYBOOK_PRESERVE_KEY_CASE,
    DEFAULT_PLAYBOOK_TASK_FIELD_MAPPING_ITEM_RENAMES,
    DEFAULT_SCRIPT_KEY_RENAMES,
)

# Playbook top-level keys stripped after binding prep (API / ES noise).
DEFAULT_PLAYBOOK_EXCLUDE_TOP_LEVEL: frozenset[str] = frozenset({
    "cacheVersn",
    "cacheversn",
    "modified",
    "created",
    "sizeInBytes",
    "sizeinbytes",
    "packID",
    "packid",
    "packName",
    "packname",
    "itemVersion",
    "itemversion",
    "fromServerVersion",
    "fromserverversion",
    "toServerVersion",
    "toserverversion",
    "propagationLabels",
    "propagationlabels",
    "definitionId",
    "definitionid",
    "vcShouldIgnore",
    "vcshouldignore",
    "commitMessage",
    "commitmessage",
    "shouldCommit",
    "shouldcommit",
    "taskIds",
    "taskids",
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
    "isOverridable",
    "isoverridable",
    "prevName",
    "prevname",
    "missingScriptsIds",
    "missingscriptids",
    "nameraw",
    "scriptids",
    "brands",
    "commands",
})

# Inner task dict (`tasks[*].task`) keys to strip.
DEFAULT_PLAYBOOK_EXCLUDE_INNER_TASK: frozenset[str] = frozenset({
    "id",
    "modified",
    "created",
    "sizeInBytes",
    "sizeinbytes",
    "cacheVersn",
    "cacheversn",
    "sequenceNumber",
    "sequencenumber",
    "primaryTerm",
    "primaryterm",
    "numericId",
    "numericid",
    "syncHash",
    "synchash",
    "indexName",
    "indexname",
    "sortValues",
    "sortvalues",
    "highlight",
    "scriptid",
    "scriptId",
})

# Top-level playbook fields expected in portable / pack-shaped YAML (reference).
DEFAULT_PLAYBOOK_INCLUDE_TOP_LEVEL: tuple[str, ...] = (
    "name",
    "id",
    "version",
    "starttaskid",
    "tasks",
    "view",
    "description",
    "inputs",
    "outputs",
    "vcShouldKeepItemLegacyProdMachine",
    "contentitemexportablefields",
)

# Script keys dropped during prepare/save (server metadata from automation/load).
DEFAULT_SCRIPT_EXCLUDE: frozenset[str] = frozenset({
    "MainEngineInfo",
    "cacheVersn",
    "created",
    "modified",
    "definitionId",
    "itemVersion",
    "fromServerVersion",
    "toServerVersion",
    "sizeInBytes",
    "commitMessage",
    "prevName",
    "propagationLabels",
    "sequenceNumber",
    "primaryTerm",
    "syncHash",
    "numericId",
    "indexName",
    "sortValues",
    "highlight",
    "packID",
    "packName",
    "user",
    "shouldCommit",
    "shouldPublish",
    "searchableName",
    "visualScript",
    "nativeImage",
    "contextKeys",
    "rawTags",
    "permitted",
    "isInternal",
    "locked",
})

DEFAULT_SCRIPT_INCLUDE_CORE: tuple[str, ...] = (
    "commonfields",
    "contentitemexportablefields",
    "vcShouldKeepItemLegacyProdMachine",
    "name",
    "script",
    "type",
    "subtype",
    "tags",
    "enabled",
    "runas",
    "runonce",
    "scripttarget",
    "pswd",
    "engineinfo",
    "mainengineinfo",
)

DEFAULT_SCRIPT_INCLUDE_OPTIONAL: tuple[str, ...] = (
    "args",
    "comment",
    "dockerimage",
    "system",
)

# Integration definition (ModuleConfiguration) keys dropped before YAML export.
DEFAULT_INTEGRATION_EXCLUDE_CONFIGURATION: frozenset[str] = frozenset({
    "id",
    "system",
    "integrationScript",
    "fromServerVersion",
    "toServerVersion",
    "cacheVersn",
    "modified",
    "created",
    "sizeInBytes",
    "definitionId",
    "itemVersion",
    "propagationLabels",
    "commitMessage",
    "shouldCommit",
    "vcShouldIgnore",
    "sequenceNumber",
    "primaryTerm",
    "syncHash",
    "numericId",
    "indexName",
    "sortValues",
    "highlight",
    "packID",
    "packName",
})

DEFAULT_INTEGRATION_EXCLUDE_CONFIG_PARAM: frozenset[str] = frozenset({
    "displayPassword",
    "hiddenPassword",
    "hiddenUsername",
    "hidden",
    "options",
})

DEFAULT_INTEGRATION_EXCLUDE_COMMAND: frozenset[str] = frozenset({
    "cartesian",
    "definitionId",
    "permitted",
    "polling",
    "execution",
    "gomAction",
    "docsHidden",
    "indicatorAction",
    "sensitive",
    "timeout",
    "deprecated",
    "hidden",
})

DEFAULT_INTEGRATION_EXCLUDE_COMMAND_ARGUMENT: frozenset[str] = frozenset({
    "deprecated",
    "hidden",
    "secret",
    "type",
})

DEFAULT_INTEGRATION_EXCLUDE_COMMAND_OUTPUT: frozenset[str] = frozenset({
    "contentPath",
})

# Script block flags omitted when false (runonce is kept to match UI export).
DEFAULT_INTEGRATION_OMIT_SCRIPT_FLAGS_WHEN_FALSE: frozenset[str] = frozenset({
    "feed",
    "isFetch",
    "isFetchEvents",
    "isFetchCredentials",
    "isFetchSamples",
    "isMappable",
    "isRemoteSyncIn",
    "isRemoteSyncOut",
    "longRunning",
    "resetContext",
})

DEFAULT_INTEGRATION_INCLUDE_TOP_LEVEL: tuple[str, ...] = (
    "commonfields",
    "vcShouldKeepItemLegacyProdMachine",
    "name",
    "display",
    "category",
    "image",
    "description",
    "detaileddescription",
    "configuration",
    "script",
    "signature",
    "restrictioncenter",
)


@dataclass(frozen=True)
class PlaybookFieldPolicy:
    exclude_top_level: frozenset[str] = DEFAULT_PLAYBOOK_EXCLUDE_TOP_LEVEL
    exclude_inner_task: frozenset[str] = DEFAULT_PLAYBOOK_EXCLUDE_INNER_TASK
    include_top_level: tuple[str, ...] = DEFAULT_PLAYBOOK_INCLUDE_TOP_LEVEL
    key_renames: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_PLAYBOOK_KEY_RENAMES))
    preserve_key_case: frozenset[str] = field(
        default_factory=lambda: frozenset(DEFAULT_PLAYBOOK_PRESERVE_KEY_CASE),
    )
    task_field_mapping_item_renames: Mapping[str, str] = field(
        default_factory=lambda: dict(DEFAULT_PLAYBOOK_TASK_FIELD_MAPPING_ITEM_RENAMES),
    )

    def effective_exclude_top_level(self) -> frozenset[str]:
        return self.exclude_top_level

    def effective_exclude_inner_task(self) -> frozenset[str]:
        return self.exclude_inner_task

    def effective_key_renames(self) -> dict[str, str]:
        return dict(self.key_renames)

    def effective_preserve_key_case(self) -> frozenset[str]:
        return self.preserve_key_case

    def effective_task_field_mapping_item_renames(self) -> dict[str, str]:
        return dict(self.task_field_mapping_item_renames)


@dataclass(frozen=True)
class ScriptFieldPolicy:
    exclude: frozenset[str] = DEFAULT_SCRIPT_EXCLUDE
    include_core: tuple[str, ...] = DEFAULT_SCRIPT_INCLUDE_CORE
    include_optional: tuple[str, ...] = DEFAULT_SCRIPT_INCLUDE_OPTIONAL
    key_renames: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_SCRIPT_KEY_RENAMES))

    def effective_exclude(self) -> frozenset[str]:
        return self.exclude

    def effective_key_renames(self) -> dict[str, str]:
        return dict(self.key_renames)


@dataclass(frozen=True)
class IntegrationFieldPolicy:
    exclude_configuration: frozenset[str] = DEFAULT_INTEGRATION_EXCLUDE_CONFIGURATION
    exclude_config_param: frozenset[str] = DEFAULT_INTEGRATION_EXCLUDE_CONFIG_PARAM
    exclude_command: frozenset[str] = DEFAULT_INTEGRATION_EXCLUDE_COMMAND
    exclude_command_argument: frozenset[str] = DEFAULT_INTEGRATION_EXCLUDE_COMMAND_ARGUMENT
    exclude_command_output: frozenset[str] = DEFAULT_INTEGRATION_EXCLUDE_COMMAND_OUTPUT
    omit_script_flags_when_false: frozenset[str] = DEFAULT_INTEGRATION_OMIT_SCRIPT_FLAGS_WHEN_FALSE
    include_top_level: tuple[str, ...] = DEFAULT_INTEGRATION_INCLUDE_TOP_LEVEL
    config_param_renames: Mapping[str, str] = field(
        default_factory=lambda: dict(DEFAULT_INTEGRATION_CONFIG_PARAM_RENAMES),
    )
    top_level_renames: Mapping[str, str] = field(
        default_factory=lambda: dict(DEFAULT_INTEGRATION_TOP_LEVEL_RENAMES),
    )

    def effective_config_param_renames(self) -> dict[str, str]:
        return dict(self.config_param_renames)

    def effective_top_level_renames(self) -> dict[str, str]:
        return dict(self.top_level_renames)


@dataclass(frozen=True)
class PortableExportFieldPolicy:
    """Built-in portable export rules (not loaded from server config)."""

    playbooks: PlaybookFieldPolicy = field(default_factory=PlaybookFieldPolicy)
    scripts: ScriptFieldPolicy = field(default_factory=ScriptFieldPolicy)
    integrations: IntegrationFieldPolicy = field(default_factory=IntegrationFieldPolicy)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": "code",
            "modules": [
                "cortex_ps_toolkit/portable_export_fields.py",
                "cortex_ps_toolkit/portable_export_remaps.py",
                "cortex_ps_toolkit/integrations/portable_yaml.py",
            ],
            "documentation": "docs/PORTABLE_EXPORT_FIELDS.md",
            "playbooks": {
                "exclude_top_level": sorted(self.playbooks.exclude_top_level),
                "exclude_inner_task": sorted(self.playbooks.exclude_inner_task),
                "include_top_level": list(self.playbooks.include_top_level),
                "key_renames": self.playbooks.effective_key_renames(),
                "preserve_key_case": sorted(self.playbooks.preserve_key_case),
                "task_field_mapping_item_renames": (
                    self.playbooks.effective_task_field_mapping_item_renames()
                ),
            },
            "scripts": {
                "exclude": sorted(self.scripts.exclude),
                "include_core": list(self.scripts.include_core),
                "include_optional": list(self.scripts.include_optional),
                "key_renames": self.scripts.effective_key_renames(),
            },
            "integrations": {
                "exclude_configuration": sorted(self.integrations.exclude_configuration),
                "exclude_config_param": sorted(self.integrations.exclude_config_param),
                "exclude_command": sorted(self.integrations.exclude_command),
                "exclude_command_argument": sorted(self.integrations.exclude_command_argument),
                "exclude_command_output": sorted(self.integrations.exclude_command_output),
                "omit_script_flags_when_false": sorted(
                    self.integrations.omit_script_flags_when_false,
                ),
                "include_top_level": list(self.integrations.include_top_level),
                "config_param_renames": self.integrations.effective_config_param_renames(),
                "top_level_renames": self.integrations.effective_top_level_renames(),
            },
        }


_BUILTIN_POLICY = PortableExportFieldPolicy()


def load_portable_export_policy(*, reload: bool = False) -> PortableExportFieldPolicy:
    """Return built-in portable export policy (``reload`` kept for API compatibility)."""
    del reload
    return _BUILTIN_POLICY


def drop_keys_case_insensitive(node: MutableMapping[str, Any], keys: Iterable[str]) -> None:
    key_set = frozenset(keys)
    lower = {k.lower() for k in key_set}
    for key in list(node.keys()):
        if key in key_set or str(key).lower() in lower:
            node.pop(key, None)
