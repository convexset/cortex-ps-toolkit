from __future__ import annotations

import pytest

from playbook_utils.context_sharing import preflight_context_updates, parse_context_update_spec
from playbook_utils.error_retry import preflight_error_updates, parse_update_spec
from tests.test_graph import make_playbook


def test_preflight_rejects_playbook_task_for_retry() -> None:
    pb = make_playbook()
    pb["tasks"]["4"] = {
        "id": "4",
        "type": "playbook",
        "task": {"name": "Sub", "playbookName": "Sub", "type": "playbook"},
        "nextTasks": {"#none#": ["5"]},
        "separateContext": True,
    }
    updates = [parse_update_spec("4:retry=15x45")]
    accepted, rejected = preflight_error_updates(pb, updates)
    assert accepted == []
    assert rejected[0]["task_id"] == "4"


def test_preflight_accepts_regular_script_for_retry() -> None:
    pb = make_playbook()
    updates = [parse_update_spec("1:retry=15x45")]
    accepted, rejected = preflight_error_updates(pb, updates)
    assert len(accepted) == 1
    assert rejected == []


def test_preflight_rejects_regular_task_for_context() -> None:
    pb = make_playbook()
    updates = [parse_context_update_spec("1:global")]
    accepted, rejected = preflight_context_updates(pb, updates)
    assert accepted == []
    assert rejected[0]["task_id"] == "1"


def test_preflight_accepts_playbook_task_for_context() -> None:
    pb = make_playbook()
    pb["tasks"]["4"] = {
        "id": "4",
        "type": "playbook",
        "task": {"name": "Sub", "playbookName": "Sub", "type": "playbook"},
        "nextTasks": {"#none#": ["5"]},
        "separateContext": True,
    }
    updates = [parse_context_update_spec("4:global")]
    accepted, rejected = preflight_context_updates(pb, updates)
    assert len(accepted) == 1
    assert rejected == []
