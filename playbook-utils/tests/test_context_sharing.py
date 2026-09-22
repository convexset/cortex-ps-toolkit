from __future__ import annotations

from playbook_utils.context_sharing import (
    ContextSharing,
    TaskContextUpdate,
    apply_playbook_context_updates,
    read_task_context_state,
)
from tests.test_graph import make_playbook


def test_apply_global_context() -> None:
    pb = make_playbook()
    pb["tasks"]["4"] = {
        "id": "4",
        "type": "playbook",
        "task": {"name": "Sub", "playbookName": "Sub", "type": "playbook"},
        "nextTasks": {"#none#": ["5"]},
        "separateContext": True,
    }
    updated = apply_playbook_context_updates(
        pb,
        [TaskContextUpdate(task_id="4", sharing=ContextSharing.GLOBAL)],
    )
    state = read_task_context_state(updated["tasks"]["4"], "4")
    assert state.sharing is ContextSharing.GLOBAL
    assert state.separate_context is False
