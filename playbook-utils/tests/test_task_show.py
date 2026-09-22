from __future__ import annotations

from typing import Dict

from playbook_utils.task_show import show_task_by_ref, show_tasks_by_name


class _FakeCache:
    def __init__(self, playbooks: Dict[str, Dict]):
        self._by_id = playbooks

    def get(self, playbook_id: str) -> Dict:
        return self._by_id[playbook_id]


def _main_playbook() -> Dict:
    return {
        "id": "pb-main",
        "name": "Main Playbook",
        "startTaskId": "0",
        "tasks": {
            "0": {"id": "0", "type": "start", "task": {"name": "", "type": "start"}},
            "335": {
                "id": "335",
                "type": "condition",
                "task": {"name": "Check Result Condition", "type": "condition"},
                "nextTasks": {"#default#": ["402"]},
            },
        },
    }


def test_show_task_by_ref() -> None:
    main = _main_playbook()
    cache = _FakeCache({"pb-main": main})
    result = show_task_by_ref(main, cache, "335")
    assert len(result.tasks) == 1
    assert result.tasks[0].task_id == "335"
    assert result.tasks[0].task_summary["name"] == "Check Result Condition"


def test_show_tasks_by_name() -> None:
    main = _main_playbook()
    cache = _FakeCache({"pb-main": main})
    result = show_tasks_by_name(main, cache, "Check Result")
    assert len(result.tasks) == 1
    assert result.tasks[0].task_id == "335"
