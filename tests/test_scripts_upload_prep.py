from __future__ import annotations

import pytest

from cortex_ps_toolkit.scripts.upload_prep import (
    prepare_script_for_save,
    script_to_yaml_export,
)


def test_prepare_script_for_save_new_copy_strips_id_and_sets_version() -> None:
    prepared = prepare_script_for_save(
        {
            "id": "source-id",
            "name": "Demo",
            "version": 9,
            "dockerImage": "demisto/python3:1.2.3",
            "cacheVersn": 1,
        },
        overwrite=False,
    )
    assert "id" not in prepared
    assert prepared["version"] == -1
    assert prepared["dockerImage"] == "demisto/python3:1.2.3"
    assert "cacheVersn" not in prepared


def test_prepare_script_for_save_overwrite_keeps_target_id() -> None:
    prepared = prepare_script_for_save(
        {"id": "source-id", "name": "Demo", "version": 9},
        target_script_id="target-id",
        overwrite=True,
    )
    assert prepared["id"] == "target-id"
    assert prepared["version"] == -1


def test_prepare_script_for_save_overwrite_requires_target_id() -> None:
    with pytest.raises(ValueError, match="target_script_id"):
        prepare_script_for_save({"id": "source-id", "name": "Demo"}, overwrite=True)


def test_script_to_yaml_export_renames_docker_image() -> None:
    exported = script_to_yaml_export({"name": "Demo", "dockerImage": "demisto/python3:1.2.3"})
    assert exported["dockerimage"] == "demisto/python3:1.2.3"
    assert "dockerImage" not in exported


def test_script_to_yaml_export_renames_arguments_to_args() -> None:
    exported = script_to_yaml_export(
        {"name": "Demo", "arguments": [{"name": "x", "required": False}]},
    )
    assert exported["args"] == [{"name": "x", "required": False}]
    assert "arguments" not in exported


def test_script_to_xsiam_yaml_export_uses_commonfields_for_overwrite() -> None:
    from cortex_ps_toolkit.scripts.upload_prep import script_to_xsiam_yaml_export

    exported = script_to_xsiam_yaml_export(
        {
            "id": "target-id",
            "version": -1,
            "name": "Demo",
            "script": "print('x')",
            "dockerImage": "demisto/python3:1.2.3",
            "runAs": "DBotWeakRole",
        },
    )
    assert "id" not in exported
    assert exported["commonfields"] == {"id": "target-id", "version": -1}
    assert exported["dockerimage"] == "demisto/python3:1.2.3"
    assert exported["runas"] == "DBotWeakRole"
