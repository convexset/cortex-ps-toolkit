"""Compare portable export shaping to XSOAR 6 UI reference YAML (scratch samples)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cortex_ps_toolkit.playbooks.portable_yaml import _strip_portable_metadata
from cortex_ps_toolkit.scripts.portable_yaml import script_to_portable_yaml_document

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "portable_export"
SCRATCH_SAMPLES = Path("/Users/weichen/Downloads/dev/scratch/xsoar-samples")

# Keys that must not appear in portable exports (from current_bundle anti-pattern).
PLAYBOOK_FORBIDDEN_TOP = frozenset({
    "cacheversn",
    "sequencenumber",
    "primaryterm",
    "modified",
    "sizeinbytes",
    "packid",
    "taskids",
    "scriptids",
    "brands",
    "commands",
    "nameraw",
})

SCRIPT_FORBIDDEN_TOP = frozenset({
    "cacheversn",
    "sequencenumber",
    "primaryterm",
    "modified",
    "sizeinbytes",
    "packid",
    "packname",
    "arguments",
    "id",
    "user",
    "searchablename",
    "system",
    "locked",
})


def _load(name: str) -> dict:
    alt = name.replace("current_bundle_export__", "tenant_export__")
    for base in (FIXTURES, SCRATCH_SAMPLES):
        for candidate in (name, alt):
            path = base / candidate
            if path.is_file():
                return yaml.safe_load(path.read_text(encoding="utf-8"))
    pytest.skip(f"reference sample missing: {name}")


def test_portable_script_document_avoids_api_metadata_keys() -> None:
    raw = _load("current_bundle_export__TEST_Show_Env.yml")
    portable = script_to_portable_yaml_document(raw, pack_source=raw)
    keys_lower = {str(k).lower() for k in portable}
    assert not keys_lower & SCRIPT_FORBIDDEN_TOP
    assert "commonfields" in keys_lower
    assert portable["commonfields"]["id"] == portable["name"]
    assert "args" in keys_lower or "arguments" not in {k.lower() for k in raw}
    raw_keys_lower = {str(k).lower() for k in raw}
    if "dockerimage" in raw_keys_lower:
        assert portable.get("dockerimage")
    assert "script" in portable


def test_portable_playbook_strip_removes_denormalized_indexes() -> None:
    raw = _load("current_bundle_export__Test_PB_Inv_Data_Main.yml")
    _strip_portable_metadata(raw)
    top_lower = {str(k).lower() for k in raw}
    assert not top_lower & PLAYBOOK_FORBIDDEN_TOP


def test_pack_playbook_export_includes_content_item_block() -> None:
    doc = _load("tenant_export__AutoFocusPolling.yml")
    assert "contentitemexportablefields" in doc
    assert doc["contentitemexportablefields"]["contentitemfields"]["packID"] == "AutoFocus"
    assert doc.get("description")
    assert doc.get("inputs")
    assert doc.get("outputs")
    assert isinstance(doc["tasks"]["0"]["view"], str)


def test_portable_integration_document_avoids_api_metadata_keys() -> None:
    from cortex_ps_toolkit.integrations.portable_yaml import configuration_to_portable_yaml_document

    raw = _load("ProtectedHTTPCall.yml")
    # Treat old bundle YAML as noisy API-shaped configuration for regression guard.
    api_row = {
        "name": raw["name"],
        "display": raw["display"],
        "category": raw["category"],
        "description": raw.get("description"),
        "detailedDescription": raw.get("detailedDescription"),
        "configuration": raw.get("configuration") or [],
        "integrationScript": raw.get("script") or {},
    }
    portable = configuration_to_portable_yaml_document(api_row)
    top_lower = {str(k).lower() for k in portable}
    assert "fromversion" not in top_lower
    assert "detailedDescription" not in portable
    first_cmd = portable["script"]["commands"][0]
    assert "cartesian" not in {str(k).lower() for k in first_cmd}


def test_pack_script_exports_include_commonfields_and_system() -> None:
    for name in ("tenant_export__RunPollingCommand.yml", "tenant_export__AddKeyToList.yml"):
        doc = _load(name)
        assert "commonfields" in doc
        assert doc["commonfields"]["id"] == doc["name"]
        assert doc.get("system") is True
        assert "contentitemexportablefields" in doc
        assert doc.get("args")


def test_tenant_reference_playbook_has_string_view() -> None:
    tenant = _load("tenant_export__Test_PB_Inv_Data_Main.yml")
    view = tenant["tasks"]["0"]["view"]
    assert isinstance(view, str)


def test_tenant_reference_script_minimal_top_level() -> None:
    tenant = _load("tenant_export__TEST_Show_Env.yml")
    allowed = {
        "commonfields",
        "name",
        "script",
        "type",
        "subtype",
        "tags",
        "enabled",
        "scripttarget",
        "pswd",
        "runonce",
        "runas",
        "engineinfo",
        "mainengineinfo",
        "vcshouldkeepitemlegacyprodmachine",
        "args",
        "dockerimage",
        "comment",
    }
    extra = {str(k).lower() for k in tenant} - allowed
    assert not extra, f"unexpected tenant keys: {sorted(extra)}"
