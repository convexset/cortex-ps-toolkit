from __future__ import annotations

import pytest

from cortex_ps_toolkit.playbooks.upload_prep import prepare_playbook_for_save


def test_prepare_playbook_for_save_new_copy_strips_ids() -> None:
    prepared = prepare_playbook_for_save(
        {
            "id": "source-id",
            "name": "Sub PB",
            "version": 3,
            "_serverMeta": "drop-me",
            "tasks": {
                "1": {
                    "taskId": "task-uuid",
                    "task": {"id": "inner-id", "version": 5, "name": "Do thing"},
                }
            },
        },
        overwrite=False,
    )
    assert "id" not in prepared
    assert prepared["version"] == -1
    assert "_serverMeta" not in prepared
    assert "taskId" not in prepared["tasks"]["1"]
    assert "id" not in prepared["tasks"]["1"]["task"]
    assert prepared["tasks"]["1"]["task"]["version"] == -1


def test_prepare_playbook_for_save_overwrite_keeps_target_id_and_task_ids() -> None:
    prepared = prepare_playbook_for_save(
        {
            "id": "source-id",
            "name": "Sub PB",
            "version": 3,
            "tasks": {
                "1": {
                    "taskId": "task-uuid",
                    "task": {"id": "inner-id", "version": 5, "name": "Do thing"},
                }
            },
        },
        target_playbook_id="target-id",
        overwrite=True,
    )
    assert prepared["id"] == "target-id"
    assert prepared["version"] == -1
    assert prepared["tasks"]["1"]["taskId"] == "task-uuid"
    assert prepared["tasks"]["1"]["task"]["id"] == "inner-id"
    assert prepared["tasks"]["1"]["task"]["version"] == -1


def test_prepare_playbook_for_save_overwrite_requires_target_id() -> None:
    with pytest.raises(ValueError, match="target_playbook_id"):
        prepare_playbook_for_save({"id": "source-id", "name": "Sub PB"}, overwrite=True)
