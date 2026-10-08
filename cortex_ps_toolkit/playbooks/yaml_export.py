"""Rename playbook API JSON keys to YAML spellings accepted by /playbook/save/yaml."""

from __future__ import annotations

from typing import Any, Mapping

from ..portable_export_fields import load_portable_export_policy
from ..portable_export_remaps import (
    DEFAULT_PLAYBOOK_KEY_RENAMES,
    DEFAULT_PLAYBOOK_PRESERVE_KEY_CASE,
)


def _playbook_rename_maps() -> tuple[dict[str, str], frozenset[str]]:
    policy = load_portable_export_policy().playbooks
    return policy.effective_key_renames(), policy.effective_preserve_key_case()


def yaml_name_for_key(
    key: str,
    *,
    canonical_to_yaml: Mapping[str, str] | None = None,
    preserve_case: frozenset[str] | None = None,
) -> str:
    renames = canonical_to_yaml if canonical_to_yaml is not None else DEFAULT_PLAYBOOK_KEY_RENAMES
    preserved = preserve_case if preserve_case is not None else frozenset(DEFAULT_PLAYBOOK_PRESERVE_KEY_CASE)
    source = str(key)
    if source in preserved:
        return source
    for name in preserved:
        if name.lower() == source.lower():
            return name
    return renames.get(source, source)


def rename_playbook_keys_for_yaml(obj: Any) -> Any:
    """Recursively rename keys to spellings ``/playbook/save/yaml`` accepts."""
    canonical_to_yaml, preserve_case = _playbook_rename_maps()
    return _rename_playbook_keys_for_yaml_impl(obj, canonical_to_yaml, preserve_case)


def _rename_playbook_keys_for_yaml_impl(
    obj: Any,
    canonical_to_yaml: Mapping[str, str],
    preserve_case: frozenset[str],
) -> Any:
    if isinstance(obj, list):
        return [
            _rename_playbook_keys_for_yaml_impl(item, canonical_to_yaml, preserve_case)
            for item in obj
        ]
    if not isinstance(obj, dict):
        return obj
    renamed: dict[str, Any] = {}
    for key, value in obj.items():
        yaml_key = yaml_name_for_key(
            str(key),
            canonical_to_yaml=canonical_to_yaml,
            preserve_case=preserve_case,
        )
        if yaml_key in renamed and yaml_key != str(key):
            continue
        renamed[yaml_key] = _rename_playbook_keys_for_yaml_impl(
            value,
            canonical_to_yaml,
            preserve_case,
        )
    return renamed
