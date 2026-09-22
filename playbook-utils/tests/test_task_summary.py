from __future__ import annotations

from playbook_utils.task_summary import compact_task_summary, format_compact_task_summary


def test_compact_task_summary_for_condition_task() -> None:
    node = {
        "type": "condition",
        "task": {"name": "Check Result Condition", "type": "condition"},
        "conditions": [
            {
                "label": "SPFpass",
                "condition": [
                    [
                        {
                            "operator": "isEqualString",
                            "left": {"value": {"simple": "ResultCondition"}, "isContext": True},
                            "right": {"value": {"simple": "SPFpass"}, "isContext": False},
                        }
                    ]
                ],
            }
        ],
        "nextTasks": {"SPFpass": ["460"], "#default#": ["402"]},
    }
    summary = compact_task_summary(node)
    assert summary["name"] == "Check Result Condition"
    assert summary["type"] == "condition"
    labels = {branch["label"] for branch in summary["branches"]}
    assert labels == {"SPFpass", "#default#"}
    text = format_compact_task_summary("335", summary)
    assert "Task 335: Check Result Condition" in text
    assert "SPFpass" in text


def test_compact_task_summary_for_set_task() -> None:
    node = {
        "type": "regular",
        "task": {"name": "Set PhishingSimulation", "scriptId": "Set", "type": "regular"},
        "scriptArguments": {
            "key": {"simple": "ResultCondition"},
            "value": {"simple": "PhishingSimulation"},
        },
    }
    summary = compact_task_summary(node)
    assert summary["arguments"]["set_key"] == "ResultCondition"
    assert summary["arguments"]["set_value"] == "PhishingSimulation"
