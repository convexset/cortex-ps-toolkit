from __future__ import annotations

from playbook_utils.task_match import (
    TaskNameMatch,
    find_matching_regular_script_task_ids,
    parse_post_task_update_spec,
    parse_task_name_match,
)
from tests.test_graph import make_playbook


def _script_task(task_id: str, title: str) -> dict:
    return {
        "id": task_id,
        "type": "regular",
        "name": title,
        "task": {"name": title, "scriptId": "Print", "type": "regular"},
    }


def test_parse_task_name_match_variants() -> None:
    assert parse_task_name_match("HttpV2") == TaskNameMatch("contains", "HttpV2", True)
    assert parse_task_name_match("contains:HttpV2:i") == TaskNameMatch("contains", "HttpV2", False)
    assert parse_task_name_match("equals:Exact Title") == TaskNameMatch("equals", "Exact Title", True)


def test_find_matching_regular_script_task_ids() -> None:
    pb = make_playbook()
    pb["tasks"]["8"] = _script_task("8", "HttpV2 | Update Case")
    pb["tasks"]["9"] = _script_task("9", "Print values")
    pb["tasks"]["10"] = {
        "id": "10",
        "type": "playbook",
        "name": "HttpV2 sub",
        "task": {"name": "HttpV2 sub", "playbookName": "Sub"},
    }
    matches = [parse_task_name_match("contains:HttpV2:i")]
    assert find_matching_regular_script_task_ids(pb, matches) == ["8"]


def test_parse_post_task_update_spec() -> None:
    match, actions = parse_post_task_update_spec("contains:HttpV2:i|retry=20x30,stop-on-error")
    assert match == TaskNameMatch("contains", "HttpV2", False)
    assert actions == "retry=20x30,stop-on-error"
