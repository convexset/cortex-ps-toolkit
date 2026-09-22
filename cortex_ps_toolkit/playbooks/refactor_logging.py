"""Map playbook-utils refactor output to cortex_ps_toolkit ops_log levels."""

from __future__ import annotations

import logging
import re

from ..ops_log import configure_ops_logging, op_debug, op_info, op_warn

_REFACTOR_PREFIX = "refactor"


def playbook_utils_log_level(message: str) -> int:
    """Return logging.DEBUG, logging.INFO, or logging.WARNING for a sink line."""
    text = message.strip()
    if not text:
        return logging.DEBUG

    if text.startswith("[debug]"):
        return logging.DEBUG

    first_line = text.splitlines()[0]
    if first_line.startswith(("Policy compare", "All-fields compare")):
        return logging.DEBUG

    if text.count("\n") >= 3:
        return logging.DEBUG

    if first_line.startswith(
        (
            "Mismatch:",
            "Could not",
            "Failed to",
            "Automation catalog unavailable",
        )
    ):
        return logging.WARNING

    if re.match(r"^Post-update skip ", first_line):
        return logging.INFO

    if first_line.startswith(
        (
            "Phase ",
            "Uploading sub-playbook",
            "Uploaded sub-playbook",
            "Uploading overwrite",
            "Refreshing cache once after",
            "Parallel post-task updates",
            "Sub-playbook descriptions were set on initial upload",
            "Upload playbook",
            "Download playbook",
            "Refresh playbook cache",
        )
    ) or first_line.startswith("Compare ") or " — started" in first_line or " — completed in" in first_line or " — failed after" in first_line:
        return logging.INFO

    return logging.INFO


def emit_playbook_utils_log(message: str) -> None:
    """Emit one playbook-utils DebugSink line using server log level rules."""
    configure_ops_logging()
    level = playbook_utils_log_level(message)
    if level == logging.DEBUG:
        op_debug("%s: %s", _REFACTOR_PREFIX, message)
    elif level == logging.WARNING:
        op_warn("%s: %s", _REFACTOR_PREFIX, message)
    else:
        op_info("%s: %s", _REFACTOR_PREFIX, message)


def emit_refactor_progress(phase: str, message: str) -> None:
    """Emit toolkit refactor orchestration progress (always INFO)."""
    configure_ops_logging()
    label = phase.strip() or "progress"
    op_info("%s [%s] — %s", _REFACTOR_PREFIX, label, message)
