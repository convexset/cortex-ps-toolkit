"""Preview/plan helpers for platform admin copy and delete."""

from __future__ import annotations

from typing import Any, Optional

from ..credentials import CredentialProfile, get_profile
from ..platforms import Platform, assert_operation_supported
from . import api
from .service import refresh_section_cache
from .types import OPERATION_BY_SECTION, AdminSection


def _indicator_platform_family(platform: Platform) -> str:
    if platform in (Platform.XSOAR6, Platform.XSOAR8):
        return "xsoar"
    if platform in (Platform.XSIAM, Platform.XDR5, Platform.AGENTIX):
        return "cortex"
    return platform.value


def _indicators_compatible(source: CredentialProfile, target: CredentialProfile) -> bool:
    return _indicator_platform_family(source.tenant_type) == _indicator_platform_family(target.tenant_type)


def _target_name(
    source: CredentialProfile,
    target: CredentialProfile,
    name: str,
    *,
    name_suffix: Optional[str],
) -> str:
    if name_suffix:
        return f"{name}{name_suffix}"
    if source.slug != target.slug:
        return name
    return f"{name}-copy"


def plan_correlation_copy(
    source_profile: CredentialProfile | str,
    target_profile: CredentialProfile | str,
    rule_names: list[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    name_suffix: Optional[str] = None,
) -> dict[str, Any]:
    source = get_profile(source_profile) if isinstance(source_profile, str) else source_profile
    target = get_profile(target_profile) if isinstance(target_profile, str) else target_profile
    assert_operation_supported(OPERATION_BY_SECTION["correlation-rules"], source.tenant_type)
    assert_operation_supported(OPERATION_BY_SECTION["correlation-rules"], target.tenant_type)

    refresh_section_cache(source, "correlation-rules")
    refresh_section_cache(target, "correlation-rules")

    entries: list[dict[str, Any]] = []
    for name in rule_names:
        source_rule = api.get_correlation_rule(source, name)
        if not source_rule:
            entries.append({"source_name": name, "action": "missing", "status": "skipped"})
            continue
        target_name = _target_name(source, target, name, name_suffix=name_suffix)
        existing = api.get_correlation_rule(target, target_name)
        if existing and stop_on_conflict:
            entries.append({"source_name": name, "target_name": target_name, "action": "conflict"})
            continue
        if existing and not overwrite:
            entries.append({"source_name": name, "target_name": target_name, "action": "skip"})
            continue
        action = "update" if existing else "copy"
        entries.append({"source_name": name, "target_name": target_name, "action": action})

    return {
        "source_profile": source.slug,
        "target_profile": target.slug,
        "section": "correlation-rules",
        "entries": entries,
        "has_conflicts": any(entry.get("action") == "conflict" for entry in entries),
    }


def plan_correlation_delete(profile: CredentialProfile | str, names: list[str]) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    assert_operation_supported(OPERATION_BY_SECTION["correlation-rules"], resolved.tenant_type)
    entries = [{"name": name, "deletable": True} for name in names]
    return {"profile": resolved.slug, "section": "correlation-rules", "entries": entries}


def plan_bioc_copy(
    source_profile: CredentialProfile | str,
    target_profile: CredentialProfile | str,
    bioc_names: list[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    name_suffix: Optional[str] = None,
) -> dict[str, Any]:
    source = get_profile(source_profile) if isinstance(source_profile, str) else source_profile
    target = get_profile(target_profile) if isinstance(target_profile, str) else target_profile
    assert_operation_supported(OPERATION_BY_SECTION["biocs"], source.tenant_type)
    assert_operation_supported(OPERATION_BY_SECTION["biocs"], target.tenant_type)

    refresh_section_cache(source, "biocs")
    refresh_section_cache(target, "biocs")

    entries: list[dict[str, Any]] = []
    for name in bioc_names:
        source_bioc = api.get_bioc(source, name)
        if not source_bioc:
            entries.append({"source_name": name, "action": "missing", "status": "skipped"})
            continue
        target_name = _target_name(source, target, name, name_suffix=name_suffix)
        existing = api.get_bioc(target, target_name)
        if existing and stop_on_conflict:
            entries.append({"source_name": name, "target_name": target_name, "action": "conflict"})
            continue
        if existing and not overwrite:
            entries.append({"source_name": name, "target_name": target_name, "action": "skip"})
            continue
        action = "update" if existing else "copy"
        entries.append({"source_name": name, "target_name": target_name, "action": action})

    return {
        "source_profile": source.slug,
        "target_profile": target.slug,
        "section": "biocs",
        "entries": entries,
        "has_conflicts": any(entry.get("action") == "conflict" for entry in entries),
    }


def plan_bioc_delete(profile: CredentialProfile | str, names: list[str]) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    assert_operation_supported(OPERATION_BY_SECTION["biocs"], resolved.tenant_type)
    entries = [{"name": name, "deletable": True} for name in names]
    return {"profile": resolved.slug, "section": "biocs", "entries": entries}


def plan_indicator_copy(
    source_profile: CredentialProfile | str,
    target_profile: CredentialProfile | str,
    indicator_ids: list[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
) -> dict[str, Any]:
    source = get_profile(source_profile) if isinstance(source_profile, str) else source_profile
    target = get_profile(target_profile) if isinstance(target_profile, str) else target_profile
    assert_operation_supported(OPERATION_BY_SECTION["indicators"], source.tenant_type)
    assert_operation_supported(OPERATION_BY_SECTION["indicators"], target.tenant_type)

    refresh_section_cache(source, "indicators")
    refresh_section_cache(target, "indicators")

    compatible = _indicators_compatible(source, target)
    entries: list[dict[str, Any]] = []
    for indicator_id in indicator_ids:
        if not compatible:
            entries.append({"source_id": indicator_id, "action": "incompatible"})
            continue
        source_doc = api.get_indicator(source, indicator_id)
        if not source_doc:
            entries.append({"source_id": indicator_id, "action": "missing"})
            continue
        lookup_value = str(
            source_doc.get("value")
            or source_doc.get("indicator")
            or indicator_id
        )
        target_existing = api.find_indicator_by_value(target, lookup_value)
        if target_existing and stop_on_conflict:
            entries.append({"source_id": indicator_id, "lookup": lookup_value, "action": "conflict"})
            continue
        if target_existing and not overwrite:
            entries.append({"source_id": indicator_id, "lookup": lookup_value, "action": "skip"})
            continue
        action = "update" if target_existing else "copy"
        entries.append({"source_id": indicator_id, "lookup": lookup_value, "action": action})

    return {
        "source_profile": source.slug,
        "target_profile": target.slug,
        "section": "indicators",
        "entries": entries,
        "has_conflicts": any(entry.get("action") == "conflict" for entry in entries),
        "compatible": compatible,
    }


def plan_indicator_delete(profile: CredentialProfile | str, indicator_ids: list[str]) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    assert_operation_supported(OPERATION_BY_SECTION["indicators"], resolved.tenant_type)
    entries = [{"id": indicator_id, "deletable": True} for indicator_id in indicator_ids]
    return {"profile": resolved.slug, "section": "indicators", "entries": entries}


def plan_section_delete(profile: CredentialProfile | str, section: AdminSection, names: list[str]) -> dict[str, Any]:
    if section == "correlation-rules":
        return plan_correlation_delete(profile, names)
    if section == "biocs":
        return plan_bioc_delete(profile, names)
    raise ValueError(f"delete preview not supported for section {section!r}")
