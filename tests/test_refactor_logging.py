"""Tests for refactor log level routing."""

from __future__ import annotations

import logging

from cortex_ps_toolkit.playbooks.refactor_logging import playbook_utils_log_level


def test_debug_artifact_lines_are_debug() -> None:
    assert playbook_utils_log_level("[debug] wrote /tmp/foo.json") == logging.DEBUG


def test_compare_summaries_are_debug() -> None:
    assert playbook_utils_log_level("Policy compare (ignored keys applied):\nline\nline") == logging.DEBUG


def test_phase_upload_lines_are_info() -> None:
    assert playbook_utils_log_level("Uploading sub-playbook 'Foo'") == logging.INFO
    assert playbook_utils_log_level("Phase 5/5: Comparing uploaded sub-playbooks") == logging.INFO


def test_mismatch_is_warning() -> None:
    assert playbook_utils_log_level("Mismatch: not uploading parent copy") == logging.WARNING
