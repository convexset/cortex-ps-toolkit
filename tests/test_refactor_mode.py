"""Tests for refactor execution mode resolution."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from cortex_ps_toolkit.playbooks.refactor_mode import (
    REFACTOR_MODE_PARALLEL,
    REFACTOR_MODE_SEQUENTIAL,
    is_parallel_mode,
    resolve_refactor_mode,
)


def test_resolve_refactor_mode_defaults_sequential() -> None:
    with patch.dict(os.environ, {}, clear=True):
        with patch("cortex_ps_toolkit.playbooks.refactor_mode.load_settings", return_value={}):
            assert resolve_refactor_mode() == REFACTOR_MODE_SEQUENTIAL


def test_resolve_refactor_mode_env_override() -> None:
    with patch.dict(os.environ, {"CORTEX_PS_REFACTOR_MODE": "parallel"}, clear=False):
        assert resolve_refactor_mode() == REFACTOR_MODE_PARALLEL


def test_resolve_refactor_mode_explicit_override() -> None:
    assert resolve_refactor_mode("parallel") == REFACTOR_MODE_PARALLEL
    assert resolve_refactor_mode("sequential") == REFACTOR_MODE_SEQUENTIAL


def test_resolve_refactor_mode_invalid_override() -> None:
    with pytest.raises(ValueError, match="refactor_mode"):
        resolve_refactor_mode("invalid")


def test_is_parallel_mode() -> None:
    assert is_parallel_mode("parallel") is True
    assert is_parallel_mode("sequential") is False
