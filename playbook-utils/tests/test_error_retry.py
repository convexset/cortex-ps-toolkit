from __future__ import annotations

import copy

from playbook_utils.error_retry import (
    ErrorHandling,
    TaskErrorUpdate,
    apply_playbook_error_updates,
    parse_update_spec,
    read_task_error_state,
    validate_task_states,
)
from tests.test_graph import make_playbook


def _regular_task(
    *,
    retry_count: str | None = None,
    retry_interval: str | None = None,
    continue_on_error: bool | None = None,
    continue_on_error_type: str = "",
    error_to: str | None = None,
) -> dict:
    node = {
        "id": "1",
        "type": "regular",
        "task": {"name": "Print", "scriptId": "Print", "type": "regular"},
        "nextTasks": {"#none#": ["2"]},
        "continueOnErrorType": continue_on_error_type,
    }
    args = {"value": {"simple": "Main"}}
    if retry_count is not None:
        args["retry-count"] = {"simple": retry_count}
    if retry_interval is not None:
        args["retry-interval"] = {"simple": retry_interval}
    node["scriptArguments"] = args
    if continue_on_error is not None:
        node["continueOnError"] = continue_on_error
    if error_to:
        node["nextTasks"]["#error#"] = [error_to]
    return node


def test_parse_update_spec() -> None:
    update = parse_update_spec("1:clear-retry,stop-on-error")
    assert update.task_id == "1"
    assert update.clear_retry is True
    assert update.error_handling is ErrorHandling.STOP

    update = parse_update_spec("8:retry=15x45,stop-on-error")
    assert update.retry_count == 15
    assert update.retry_interval == 45


def test_read_task_error_state() -> None:
    state = read_task_error_state(_regular_task(retry_count="20", retry_interval="60"), "1")
    assert state.retry.count == 20
    assert state.retry.interval == 60
    assert state.error_handling is ErrorHandling.STOP

    state = read_task_error_state(
        _regular_task(continue_on_error=True, continue_on_error_type="errorPath", error_to="10"),
        "6",
    )
    assert state.error_handling is ErrorHandling.ERROR_PATH
    assert state.has_error_path is True


def test_apply_clear_retry_and_stop() -> None:
    pb = make_playbook()
    pb["tasks"]["1"] = _regular_task(retry_count="20", retry_interval="60")
    updated = apply_playbook_error_updates(
        pb,
        [TaskErrorUpdate(task_id="1", clear_retry=True, error_handling=ErrorHandling.STOP)],
    )
    state = read_task_error_state(updated["tasks"]["1"], "1")
    assert state.retry.count is None
    assert state.retry.interval is None
    assert state.error_handling is ErrorHandling.STOP


def test_apply_add_retry_and_stop_from_continue() -> None:
    pb = make_playbook()
    pb["tasks"]["8"] = _regular_task(continue_on_error=True)
    updated = apply_playbook_error_updates(
        pb,
        [
            TaskErrorUpdate(
                task_id="8",
                retry_count=15,
                retry_interval=45,
                error_handling=ErrorHandling.STOP,
            )
        ],
    )
    state = read_task_error_state(updated["tasks"]["8"], "8")
    assert state.retry.count == 15
    assert state.retry.interval == 45
    assert state.error_handling is ErrorHandling.STOP
    assert state.continue_on_error is None


def test_unchanged_task_validation() -> None:
    pb = make_playbook()
    pb["tasks"]["6"] = _regular_task(
        continue_on_error=True,
        continue_on_error_type="errorPath",
        error_to="10",
    )
    before = read_task_error_state(pb["tasks"]["6"], "6")
    updated = apply_playbook_error_updates(
        pb,
        [TaskErrorUpdate(task_id="1", clear_retry=True, error_handling=ErrorHandling.STOP)],
    )
    after = read_task_error_state(updated["tasks"]["6"], "6")
    assert after == before
    assert validate_task_states(updated, {"6": before}) == []
