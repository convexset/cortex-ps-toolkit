from __future__ import annotations

from typing import Dict

from playbook_utils.task_input_search import (
    collect_task_inputs,
    format_task_input_search_text,
    inputs_contain,
    search_task_inputs,
)


class _FakeCache:
    def __init__(self, playbooks: Dict[str, Dict]):
        self._by_id = playbooks
        self._by_name = {pb["name"]: pb for pb in playbooks.values()}

    def get(self, playbook_id: str) -> Dict:
        playbook = self._by_id.get(playbook_id)
        if playbook is None:
            raise KeyError(playbook_id)
        return playbook

    def resolve(self, name_or_id: str) -> Dict:
        if name_or_id in self._by_id:
            return self._by_id[name_or_id]
        playbook = self._by_name.get(name_or_id)
        if playbook is None:
            raise KeyError(name_or_id)
        return playbook


def _main_playbook() -> Dict:
    return {
        "id": "pb-main",
        "name": "Main Playbook",
        "startTaskId": "0",
        "tasks": {
            "0": {
                "id": "0",
                "type": "start",
                "task": {"name": "", "type": "start"},
                "nextTasks": {"#none#": ["1"]},
            },
            "1": {
                "id": "1",
                "type": "regular",
                "task": {"name": "Set issue title", "type": "regular"},
                "scriptArguments": {
                    "value": {"simple": "${issue.name}"},
                },
            },
            "2": {
                "id": "2",
                "type": "playbook",
                "task": {
                    "name": "Run Sub",
                    "type": "playbook",
                    "playbookName": "Child Playbook",
                },
            },
        },
    }


def _child_playbook() -> Dict:
    return {
        "id": "pb-child",
        "name": "Child Playbook",
        "startTaskId": "0",
        "tasks": {
            "0": {
                "id": "0",
                "type": "start",
                "task": {"name": "", "type": "start"},
                "nextTasks": {"#none#": ["10"]},
            },
            "10": {
                "id": "10",
                "type": "regular",
                "task": {"name": "Child HttpV2", "type": "regular"},
                "scriptArguments": {
                    "body": {"complex": {"root": "issue.name", "filters": []}},
                },
            },
        },
    }


def test_inputs_contain_is_case_insensitive() -> None:
    node = {
        "scriptArguments": {
            "value": {"simple": "${Issue.Name}"},
        }
    }
    assert inputs_contain(node, "issue.name")
    assert not inputs_contain(node, "missing.field")


def test_collect_task_inputs_serializes_nested_dicts() -> None:
    node = _main_playbook()["tasks"]["1"]
    payload = collect_task_inputs(node)
    assert "scriptArguments" in payload
    assert payload["scriptArguments"]["value"]["simple"] == "${issue.name}"


def test_search_task_inputs_finds_matches_in_sub_playbooks() -> None:
    cache = _FakeCache(
        {
            "pb-main": _main_playbook(),
            "pb-child": _child_playbook(),
        }
    )
    result = search_task_inputs(_main_playbook(), cache, "issue.name")
    assert len(result.matches) == 2
    paths = {match.nesting_path_text for match in result.matches}
    assert "Main Playbook" in paths
    assert "Main Playbook > Child Playbook" in paths
    task_ids = {match.task_id for match in result.matches}
    assert task_ids == {"1", "10"}


def test_format_task_input_search_text_lists_path() -> None:
    cache = _FakeCache(
        {
            "pb-main": _main_playbook(),
            "pb-child": _child_playbook(),
        }
    )
    result = search_task_inputs(_main_playbook(), cache, "issue.name")
    text = format_task_input_search_text(result)
    assert "Matches: 2" in text
    assert "Main Playbook > Child Playbook" in text
    assert "Set issue title" in text
