"""Parse and validate post-refactor error-handling specs (``MATCH|actions``)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Sequence

MatchMode = Literal["contains", "equals"]
ErrorAction = Literal["stop-on-error", "continue", "error-path"]

_CLUSTER_RE = re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s*$")


@dataclass(frozen=True)
class PostTaskUpdateSpec:
    match_mode: MatchMode
    pattern: str
    case_insensitive: bool = False
    retry_count: int | None = None
    retry_interval: int | None = None
    clear_retry: bool = False
    error_handling: ErrorAction | None = None

    def to_spec(self) -> str:
        match_part = f"{self.match_mode}:{self.pattern}"
        if self.case_insensitive:
            match_part += ":i"
        actions: list[str] = []
        if self.clear_retry:
            actions.append("clear-retry")
        if self.retry_count is not None:
            if self.retry_interval is None:
                raise ValueError("retry-interval is required when retry-count is set")
            actions.append(f"retry={self.retry_count}x{self.retry_interval}")
        if self.error_handling:
            actions.append(self.error_handling)
        if not actions:
            raise ValueError("At least one action is required (retry, clear-retry, or error handling)")
        return f"{match_part}|{','.join(actions)}"


def parse_task_name_match(spec: str) -> tuple[MatchMode, str, bool]:
    text = spec.strip()
    if not text:
        raise ValueError("task name match is empty")

    case_sensitive = True
    if text.endswith(":i"):
        case_sensitive = False
        text = text[:-2]

    if text.startswith("contains:"):
        pattern = text[len("contains:") :]
        if not pattern:
            raise ValueError(f"contains match missing pattern: {spec!r}")
        return "contains", pattern, not case_sensitive

    if text.startswith("equals:"):
        pattern = text[len("equals:") :]
        if not pattern:
            raise ValueError(f"equals match missing pattern: {spec!r}")
        return "equals", pattern, not case_sensitive

    return "contains", text, not case_sensitive


def parse_post_task_update_spec(spec: str) -> PostTaskUpdateSpec:
    """Parse ``MATCH|actions`` for post-refactor in-place updates."""
    if "|" not in spec:
        raise ValueError(
            f"post-task-update must look like MATCH|actions (got {spec!r}); "
            "example: contains:HttpV2:i|retry=30x30,stop-on-error"
        )
    match_part, actions_part = spec.split("|", 1)
    match_part = match_part.strip()
    actions_part = actions_part.strip()
    if not match_part or not actions_part:
        raise ValueError(f"post-task-update missing match or actions: {spec!r}")

    mode, pattern, case_insensitive = parse_task_name_match(match_part)
    parsed = PostTaskUpdateSpec(
        match_mode=mode,
        pattern=pattern,
        case_insensitive=case_insensitive,
    )

    clear_retry = False
    retry_count: int | None = None
    retry_interval: int | None = None
    error_handling: ErrorAction | None = None

    for raw_action in actions_part.split(","):
        action = raw_action.strip()
        if not action:
            continue
        if action == "clear-retry":
            clear_retry = True
        elif action == "stop-on-error":
            error_handling = "stop-on-error"
        elif action == "continue":
            error_handling = "continue"
        elif action == "error-path":
            error_handling = "error-path"
        elif action.startswith("retry="):
            payload = action.split("=", 1)[1]
            if "x" not in payload:
                raise ValueError(f"retry action must look like retry=NxI (got {action!r})")
            count_text, interval_text = payload.split("x", 1)
            retry_count = int(count_text)
            retry_interval = int(interval_text)
            if retry_count <= 0 or retry_interval <= 0:
                raise ValueError("retry count and interval must be positive integers")
        else:
            raise ValueError(f"unknown action {action!r} in {spec!r}")

    return PostTaskUpdateSpec(
        match_mode=mode,
        pattern=pattern,
        case_insensitive=case_insensitive,
        retry_count=retry_count,
        retry_interval=retry_interval,
        clear_retry=clear_retry,
        error_handling=error_handling,
    )


def validate_post_task_update_specs(specs: Sequence[str]) -> list[str]:
    """Return human-readable validation errors (empty if all specs are valid)."""
    errors: list[str] = []
    for index, spec in enumerate(specs, start=1):
        text = str(spec or "").strip()
        if not text:
            errors.append(f"Error handling rule {index}: spec is empty")
            continue
        try:
            parsed = parse_post_task_update_spec(text)
            parsed.to_spec()
        except ValueError as exc:
            errors.append(f"Error handling rule {index}: {exc}")
    return errors


def validate_leaf_task(value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return "Leaf extract task id or name is required"
    return None


def validate_cluster(value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return "Cluster range is required"
    match = _CLUSTER_RE.match(text)
    if not match:
        return "Cluster must look like START:END (e.g. 21:52)"
    start, end = int(match.group(1)), int(match.group(2))
    if start >= end:
        return "Cluster START must be less than END"
    return None
