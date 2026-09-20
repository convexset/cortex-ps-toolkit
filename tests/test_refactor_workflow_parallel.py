"""Tests for parallel refactor workflow orchestration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.playbooks.refactor_workflow import execute_refactor_workflow


@patch("cortex_ps_toolkit.playbooks.refactor_workflow.clear_refactor_playbooks")
@patch("cortex_ps_toolkit.playbooks.refactor_workflow.get_refactor_preset")
@patch("cortex_ps_toolkit.playbooks.refactor_workflow.resolve_workflow_preset")
@patch("cortex_ps_toolkit.playbooks.refactor_workflow.GraphExecutor")
@patch("cortex_ps_toolkit.playbooks.refactor_workflow.execute_refactor")
def test_workflow_parallel_runs_graph_for_multiple_steps(
    mock_execute: MagicMock,
    mock_executor_cls: MagicMock,
    mock_resolve: MagicMock,
    mock_get_preset: MagicMock,
    mock_clear: MagicMock,
) -> None:
    mock_get_preset.return_value = {"id": "wf", "profile": "lab", "steps": ["a", "b"]}
    mock_resolve.return_value = {
        "profile": "lab",
        "clear_refactor_prefix": "[REFACTOR-",
        "resolved_steps": [
            {"id": "step-a", "label": "A", "profile": "lab", "leaf_tasks": ["1"]},
            {"id": "step-b", "label": "B", "profile": "lab", "leaf_tasks": ["2"]},
        ],
    }
    mock_clear.return_value = {"delete_result": {"counts": {"deleted": 0}}}

    step_a_result = {"step": "step-a", "label": "A", "elapsed_ms": 10, "ok": True, "result": {"ok": True}}
    step_b_result = {"step": "step-b", "label": "B", "elapsed_ms": 12, "ok": True, "result": {"ok": True}}

    def _run_graph(graph):
        for task_id, task in graph.tasks().items():
            task.fn()
        from cortex_ps_toolkit.runtime.graph import GraphRunResult, TaskState

        return GraphRunResult(
            ok=True,
            tasks={
                "step-a": TaskState(id="step-a", status="success", result=step_a_result),
                "step-b": TaskState(id="step-b", status="success", result=step_b_result),
            },
        )

    mock_executor_cls.return_value.run.side_effect = _run_graph
    mock_execute.return_value = {"ok": True}

    result = execute_refactor_workflow("wf", refactor_mode="parallel")

    assert result["ok"] is True
    assert result["refactor_mode"] == "parallel"
    assert len(result["steps"]) == 3
    mock_executor_cls.return_value.run.assert_called_once()
    assert mock_execute.call_count == 2
    cache_keys = {call.kwargs.get("job_cache_key") for call in mock_execute.call_args_list}
    assert cache_keys == {"wf/step-a", "wf/step-b"}
