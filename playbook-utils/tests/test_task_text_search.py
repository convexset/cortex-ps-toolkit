from __future__ import annotations

from typing import Dict

from playbook_utils.task_text_search import search_task_text, task_text_contains


class _FakeCache:
    def __init__(self, playbooks: Dict[str, Dict]):
        self._by_id = playbooks

    def get(self, playbook_id: str) -> Dict:
        return self._by_id[playbook_id]

    def resolve(self, name_or_id: str) -> Dict:
        return self._by_id[name_or_id]


def test_task_text_contains_matches_branch_label() -> None:
    node = {
        "type": "condition",
        "task": {"name": "Check Result", "type": "condition"},
        "conditions": [{"label": "SPFpass", "condition": []}],
    }
    assert task_text_contains(node, "SPFpass")
    assert not task_text_contains(node, "missing")


def test_search_task_text_finds_match_in_sub_playbook() -> None:
    main = {
        "id": "pb-main",
        "name": "Main",
        "tasks": {
            "0": {"id": "0", "type": "start", "task": {"name": "", "type": "start"}},
            "1": {
                "id": "1",
                "type": "playbook",
                "task": {"name": "Sub call", "type": "playbook", "playbookId": "pb-sub"},
            },
        },
    }
    sub = {
        "id": "pb-sub",
        "name": "Sub Playbook",
        "tasks": {
            "10": {
                "id": "10",
                "type": "regular",
                "task": {"name": "Set SPFpass", "type": "regular", "scriptId": "Set"},
                "scriptArguments": {
                    "key": {"simple": "ResultCondition"},
                    "value": {"simple": "SPFpass"},
                },
            },
        },
    }
    cache = _FakeCache({"pb-main": main, "pb-sub": sub})
    result = search_task_text(main, cache, "SPFpass")
    assert len(result.matches) == 1
    assert result.matches[0].task_id == "10"
    assert result.matches[0].nesting_path_text == "Main > Sub Playbook"
