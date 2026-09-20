"""Structured operation logging for server and copy workflows."""

from __future__ import annotations

import logging
import os

LOGGER = logging.getLogger("cortex_ps_toolkit")


def configure_ops_logging() -> None:
    """Attach a stderr handler once (INFO by default; DEBUG when CORTEX_PS_DEBUG=1)."""
    if LOGGER.handlers:
        return
    level = logging.DEBUG if os.environ.get("CORTEX_PS_DEBUG") else logging.INFO
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    LOGGER.setLevel(level)
    LOGGER.addHandler(handler)
    LOGGER.propagate = False


def _emit(level: str, text: str) -> None:
    try:
        from .server.events import publish_log, publish_notification

        publish_log(level, text)
        if level in ("warning", "error"):
            publish_notification(text, level=level, auto_dismiss_ms=8000)
    except Exception:
        pass


def op_info(message: str, *args: object) -> None:
    text = message % args if args else message
    LOGGER.info(text)
    _emit("info", text)


def op_debug(message: str, *args: object) -> None:
    text = message % args if args else message
    LOGGER.debug(text)
    _emit("debug", text)
