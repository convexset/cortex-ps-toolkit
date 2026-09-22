"""Write human + machine-readable debug artifacts."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional

from .keys import JsonDict

LogHandler = Callable[[str], None]
_log_handler_stack: list[LogHandler] = []


def active_log_handler() -> Optional[LogHandler]:
    if not _log_handler_stack:
        return None
    return _log_handler_stack[-1]


@contextmanager
def log_handler_context(handler: LogHandler) -> Iterator[None]:
    """Route DebugSink.log lines to *handler* instead of stdout."""
    _log_handler_stack.append(handler)
    try:
        yield
    finally:
        _log_handler_stack.pop()


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def slug(text: str, fallback: str = "playbook") -> str:
    chars = []
    for ch in text.strip() or fallback:
        if ch.isalnum():
            chars.append(ch)
        elif ch in "-._":
            chars.append(ch)
        else:
            chars.append("-")
    collapsed = "".join(chars).strip("-") or fallback
    return collapsed[:80]


class DebugSink:
    def __init__(self, directory: Optional[Path], *, verbose: bool = True):
        self.directory = Path(directory) if directory else None
        self.verbose = verbose
        if self.directory:
            self.directory.mkdir(parents=True, exist_ok=True)

    def log(self, message: str) -> None:
        handler = active_log_handler()
        if handler is not None:
            handler(message)
            return
        if self.verbose:
            print(message)

    def write_json(self, name: str, payload: Any) -> Optional[Path]:
        if not self.directory:
            return None
        path = self.directory / name
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        self.log(f"[debug] wrote {path}")
        return path

    def write_text(self, name: str, text: str) -> Optional[Path]:
        if not self.directory:
            return None
        path = self.directory / name
        path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        self.log(f"[debug] wrote {path}")
        return path

    def write_mapping(self, name: str, payload: Mapping[str, Any]) -> Optional[Path]:
        return self.write_json(name, dict(payload))
