from __future__ import annotations

from typing import Dict

from playbook_utils.condition_branches import (
    analyze_condition_branches,
    extract_branch_specs,
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


def _checklist_sub() -> Dict:
    return {
        "id": "pb-sub",
        "name": "CheckList Sub",
        "startTaskId": "0",
        "outputs": [{"contextPath": "ResultCondition"}],
        "tasks": {
            "0": {
                "id": "0",
                "type": "start",
                "task": {"name": "", "type": "start"},
                "nextTasks": {"#none#": ["9"]},
            },
            "9": {
                "id": "9",
                "type": "regular",
                "task": {"name": "Set PhishingSimulation", "scriptId": "Set", "type": "regular"},
                "scriptArguments": {
                    "key": {"simple": "ResultCondition"},
                    "value": {"simple": "PhishingSimulation"},
                },
            },
        },
    }


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
                "nextTasks": {"#none#": ["334"]},
            },
            "334": {
                "id": "334",
                "type": "playbook",
                "task": {
                    "name": "CheckList",
                    "type": "playbook",
                    "playbookId": "pb-sub",
                },
                "nextTasks": {"#none#": ["335"]},
            },
            "335": {
                "id": "335",
                "type": "condition",
                "task": {"name": "Check Result Condition", "type": "condition"},
                "conditions": [
                    {
                        "label": "PhishingSimulation",
                        "condition": [
                            [
                                {
                                    "operator": "isEqualString",
                                    "left": {
                                        "value": {"simple": "ResultCondition"},
                                        "isContext": True,
                                    },
                                    "right": {
                                        "value": {"simple": "PhishingSimulation"},
                                        "isContext": False,
                                    },
                                }
                            ]
                        ],
                    }
                ],
                "nextTasks": {
                    "#default#": ["402"],
                    "PhishingSimulation": ["454"],
                },
            },
        },
    }


def test_extract_branch_specs_reads_labels_and_defaults() -> None:
    node = _main_playbook()["tasks"]["335"]
    specs = extract_branch_specs(node)
    labels = [spec.label for spec in specs]
    assert "PhishingSimulation" in labels
    assert "#default#" in labels
    sim = next(spec for spec in specs if spec.label == "PhishingSimulation")
    assert sim.variables[0].expression == "ResultCondition"
    assert sim.expected_values == ["PhishingSimulation"]


def test_analyze_condition_branches_finds_sub_playbook_set() -> None:
    cache = _FakeCache({"pb-main": _main_playbook(), "pb-sub": _checklist_sub()})
    report = analyze_condition_branches(
        _main_playbook(),
        cache,
        playbook=_main_playbook(),
        task_id="335",
        nesting_path=["Main Playbook"],
    )
    branch = next(item for item in report.branches if item.label == "PhishingSimulation")
    assert branch.assignments[0].task_id == "9"
    assert branch.assignments[0].assignment_kind == "set"
    assert branch.assignments[0].assigned_value == "PhishingSimulation"
    assert "CheckList Sub" in branch.assignments[0].nesting_path_text
