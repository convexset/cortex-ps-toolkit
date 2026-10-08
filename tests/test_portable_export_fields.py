"""Built-in portable export field policy (code-only)."""

from __future__ import annotations

from cortex_ps_toolkit import portable_export_fields as pef
from cortex_ps_toolkit.playbooks import portable_yaml as pb_portable
from cortex_ps_toolkit.playbooks.yaml_export import rename_playbook_keys_for_yaml
from cortex_ps_toolkit.scripts.upload_prep import script_to_yaml_export


def test_builtin_playbook_excludes() -> None:
    policy = pef.load_portable_export_policy()
    top = policy.playbooks.effective_exclude_top_level()
    assert "cacheVersn" in top
    assert "packID" in top


def test_strip_portable_metadata_drops_es_keys() -> None:
    doc = {"name": "PB", "cacheVersn": 1, "tasks": {}}
    pb_portable._strip_portable_metadata(doc)
    assert "cacheVersn" not in doc


def test_policy_to_dict_documents_source() -> None:
    payload = pef.load_portable_export_policy().to_dict()
    assert payload["source"] == "code"
    assert "exclude_top_level" in payload["playbooks"]
    assert "key_renames" in payload["playbooks"]
    assert "exclude" in payload["scripts"]
    assert "exclude_command" in payload["integrations"]


def test_playbook_key_rename_builtin() -> None:
    doc = {"nextTasks": {"#none#": [0]}}
    renamed = rename_playbook_keys_for_yaml(doc)
    assert "nexttasks" in renamed


def test_script_key_rename_builtin() -> None:
    out = script_to_yaml_export({"name": "S", "arguments": [], "dockerImage": "demisto/python3"})
    assert "args" in out
    assert out.get("dockerimage") == "demisto/python3"
    assert "arguments" not in out
