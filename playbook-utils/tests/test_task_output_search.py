from __future__ import annotations

from typing import Dict

from playbook_utils.task_output_search import (
    outputs_contain,
    script_filter_matches,
    search_task_outputs,
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
            },
            "1": {
                "id": "1",
                "type": "regular",
                "task": {
                    "name": "Set full name",
                    "type": "regular",
                    "scriptId": "Builtin|||setIssue",
                },
                "scriptArguments": {
                    "fullname": {"simple": "Alice Example"},
                },
            },
            "2": {
                "id": "2",
                "type": "regular",
                "task": {
                    "name": "Set status",
                    "type": "regular",
                    "scriptId": "Builtin|||setIssueStatus",
                },
                "scriptArguments": {
                    "status": {"simple": "In Progress"},
                },
            },
            "3": {
                "id": "3",
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
            },
            "10": {
                "id": "10",
                "type": "regular",
                "task": {
                    "name": "Set issue name field",
                    "type": "regular",
                    "scriptId": "Builtin|||setIssue",
                },
                "scriptArguments": {
                    "name": {"simple": "Phishing alert"},
                },
            },
        },
    }


def test_script_filter_matches_set_issue_only() -> None:
    set_issue = {"scriptId": "Builtin|||setIssue"}
    set_status = {"scriptId": "Builtin|||setIssueStatus"}
    assert script_filter_matches(set_issue, "setIssue")
    assert not script_filter_matches(set_status, "setIssue")


def test_outputs_contain_matches_field_names() -> None:
    node = _main_playbook()["tasks"]["1"]
    assert outputs_contain(node, "fullname")
    assert outputs_contain(node, "name")
    assert not outputs_contain(node, "status")


def test_search_task_outputs_filters_by_script_and_needle() -> None:
    cache = _FakeCache(
        {
            "pb-main": _main_playbook(),
            "pb-child": _child_playbook(),
        }
    )
    result = search_task_outputs(
        _main_playbook(),
        cache,
        "name",
        script_filter="setIssue",
    )
    assert len(result.matches) == 2
    task_ids = {match.task_id for match in result.matches}
    assert task_ids == {"1", "10"}
    assert all(match.script_binding == "Builtin|||setIssue" for match in result.matches)
    assert any("fullname" in match.matched_fields for match in result.matches if match.task_id == "1")
    assert any("name" in match.matched_fields for match in result.matches if match.task_id == "10")
