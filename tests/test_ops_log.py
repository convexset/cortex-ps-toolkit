from __future__ import annotations

from cortex_ps_toolkit.ops_log import LOGGER, configure_ops_logging, op_timed_operation


def test_op_timed_operation_logs_start_and_complete_ms(capsys) -> None:
    LOGGER.handlers.clear()
    configure_ops_logging()
    label = "Refresh playbooks cache for lab [ops-log-test]"
    with op_timed_operation(label) as detail:
        detail["summary"] = "42 item(s)"
    err = capsys.readouterr().err
    assert f"{label} — started" in err
    assert "completed in" in err and "ms" in err and "42 item(s)" in err
