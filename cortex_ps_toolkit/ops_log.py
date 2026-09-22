"""Structured operation logging for server and copy workflows."""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from .server_config import debug_truncation_threshold, server_log_level_name

LOGGER = logging.getLogger("cortex_ps_toolkit")

_LEVEL_BY_NAME = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


def configure_ops_logging() -> None:
    """Attach a stderr handler using server config log level."""
    if LOGGER.handlers:
        return

    level_name = server_log_level_name()
    if os.environ.get("CORTEX_PS_DEBUG") == "1":
        level = logging.DEBUG
    else:
        level = _LEVEL_BY_NAME.get(level_name, logging.INFO)

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


def _emit(level: str, text: str, *, persistent: bool = False) -> None:
    try:
        from .server.events import publish_log, publish_notification

        publish_log(level, text)
        if level in ("warning", "error"):
            publish_notification(
                text,
                level=level,
                auto_dismiss_ms=0 if persistent else 8000,
            )
    except Exception:
        pass


@contextmanager
def op_timed_operation(label: str, *args: object) -> Iterator[dict[str, Any]]:
    """Log INFO when an asset/cache operation starts and completes, with duration in milliseconds."""
    text = label % args if args else label
    started = time.monotonic()
    op_info("%s — started", text)
    detail: dict[str, Any] = {}
    try:
        yield detail
    except Exception:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        op_error("%s — failed after %dms", text, elapsed_ms)
        raise
    else:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        suffix = detail.get("summary")
        if suffix:
            op_info("%s — completed in %dms (%s)", text, elapsed_ms, suffix)
        else:
            op_info("%s — completed in %dms", text, elapsed_ms)


@contextmanager
def op_action(message: str, *args: object) -> Iterator[None]:
    """Log INFO start/end timestamps and duration for a multi-step operation."""
    label = message % args if args else message
    started_wall = datetime.now(timezone.utc)
    started = time.monotonic()
    op_info("%s — started at %s", label, started_wall.strftime("%Y-%m-%dT%H:%M:%SZ"))
    try:
        yield
    except Exception:
        elapsed = time.monotonic() - started
        op_error("%s — failed after %.1fs (started %s)", label, elapsed, started_wall.strftime("%H:%M:%S"))
        raise
    else:
        elapsed = time.monotonic() - started
        op_info(
            "%s — completed in %.1fs (started %s, ended %s)",
            label,
            elapsed,
            started_wall.strftime("%H:%M:%S"),
            datetime.now(timezone.utc).strftime("%H:%M:%S"),
        )


def _looks_binary_text(text: str) -> bool:
    if not text:
        return False
    sample = text[:512]
    non_printable = sum(1 for ch in sample if ord(ch) < 32 and ch not in "\t\n\r")
    return non_printable / max(len(sample), 1) > 0.15


def _summarize_binary(value: bytes | bytearray) -> str:
    return f"<binary payload, {len(value)} bytes>"


def _summarize_for_log(value: Any, *, depth: int = 0) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return _summarize_binary(value)
    if isinstance(value, str) and _looks_binary_text(value):
        return f"<binary-like text, {len(value)} chars>"
    if isinstance(value, Mapping):
        if depth >= 4:
            return f"<object, {len(value)} key(s)>"
        return {str(key): _summarize_for_log(item, depth=depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        if depth >= 4:
            return f"<{type(value).__name__}, {len(value)} item(s)>"
        return [_summarize_for_log(item, depth=depth + 1) for item in value]
    return value


def truncate_for_log(value: Any, *, threshold: Optional[int] = None) -> str:
    limit = threshold if threshold is not None else debug_truncation_threshold()
    if value is None:
        return "null"
    if isinstance(value, (bytes, bytearray)):
        return _summarize_binary(value)
    if isinstance(value, str) and _looks_binary_text(value):
        return f"<binary-like text, {len(value)} chars>"
    if isinstance(value, Mapping) and LOGGER.isEnabledFor(logging.DEBUG):
        summarized = _summarize_for_log(value)
        try:
            text = json.dumps(summarized, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            text = repr(summarized)
    elif isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            text = repr(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}… [truncated, {len(text)} chars total]"


def op_info(message: str, *args: object) -> None:
    text = message % args if args else message
    LOGGER.info(text)
    _emit("info", text)


def op_debug(message: str, *args: object) -> None:
    text = message % args if args else message
    LOGGER.debug(text)
    _emit("debug", text)


def op_warn(message: str, *args: object, persistent: bool = False) -> None:
    text = message % args if args else message
    LOGGER.warning(text)
    _emit("warning", text, persistent=persistent)


def op_error(
    message: str,
    *args: object,
    exc: Optional[BaseException] = None,
    persistent: bool = True,
) -> None:
    text = message % args if args else message
    if exc is not None:
        LOGGER.error(text, exc_info=exc)
    else:
        LOGGER.error(text)
    _emit("error", text, persistent=persistent)


def log_data_read(operation: str, *, detail: str = "", payload: Any = None) -> None:
    message = f"READ {operation}"
    if detail:
        message = f"{message} — {detail}"
    op_info(message)
    if payload is not None and LOGGER.isEnabledFor(logging.DEBUG):
        op_debug("  payload: %s", truncate_for_log(payload))


def log_data_write(operation: str, *, detail: str = "", payload: Any = None) -> None:
    message = f"WRITE {operation}"
    if detail:
        message = f"{message} — {detail}"
    op_info(message)
    if payload is not None and LOGGER.isEnabledFor(logging.DEBUG):
        op_debug("  payload: %s", truncate_for_log(payload))


def log_api_request(
    method: str,
    url: str,
    action: str,
    *,
    request: Any = None,
) -> None:
    if LOGGER.isEnabledFor(logging.DEBUG):
        op_debug("API %s %s — %s", method.upper(), url, action)
        if request is not None:
            op_debug("  request: %s", truncate_for_log(request))


def log_api_response(
    method: str,
    url: str,
    action: str,
    *,
    response: Any = None,
    status_code: Optional[int] = None,
) -> None:
    if LOGGER.isEnabledFor(logging.DEBUG):
        if status_code is not None:
            op_debug("  status: %s", status_code)
        if response is not None:
            op_debug("  response: %s", truncate_for_log(response))
