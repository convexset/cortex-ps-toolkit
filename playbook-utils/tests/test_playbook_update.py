from __future__ import annotations

from playbook_utils.playbook_update import expand_error_updates_from_matches
from playbook_utils.task_match import parse_task_name_match
from tests.test_graph import make_playbook


def test_expand_error_updates_from_matches() -> None:
    pb = make_playbook()
    pb["tasks"]["8"] = {
        "id": "8",
        "type": "regular",
        "name": "HttpV2 | Update Case",
        "task": {"name": "HttpV2 | Update Case", "scriptId": "HttpV2", "type": "regular"},
    }
    updates, rejected = expand_error_updates_from_matches(
        pb,
        [parse_task_name_match("contains:HttpV2:i")],
        "retry=20x30,stop-on-error",
    )
    assert rejected == []
    assert [update.task_id for update in updates] == ["8"]
    assert updates[0].retry_count == 20
    assert updates[0].retry_interval == 30
