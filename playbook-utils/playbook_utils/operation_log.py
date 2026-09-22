"""INFO-level start/complete timing for tenant asset operations (playbook-utils)."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Callable, Iterator, Optional

_INFO_LOGGER: Optional[Callable[[str], None]] = None
_FALLBACK = logging.getLogger("playbook_utils")


def set_info_logger(fn: Optional[Callable[[str], None]]) -> None:
    """Route timed operation lines (toolkit sets this to ``ops_log.op_info``)."""
    global _INFO_LOGGER
    _INFO_LOGGER = fn


def _info(message: str, *args: object) -> None:
    text = message % args if args else message
    if _INFO_LOGGER is not None:
        _INFO_LOGGER(text)
        return
    _FALLBACK.info(text)


@contextmanager
def timed_operation(label: str, *args: object) -> Iterator[None]:
    text = label % args if args else label
    started = time.monotonic()
    _info("%s — started", text)
    try:
        yield
    except Exception:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        _info("%s — failed after %dms", text, elapsed_ms)
        raise
    else:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        _info("%s — completed in %dms", text, elapsed_ms)
