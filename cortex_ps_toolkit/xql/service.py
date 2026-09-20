"""XQL query run orchestration (start → poll → optional stream)."""

from __future__ import annotations

import gzip
import json
import time
from typing import Any, Mapping, Optional

from ..credentials import CredentialProfile, get_profile
from . import api


def _parse_stream_rows(raw: bytes) -> list[dict[str, Any]]:
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    text = raw.decode("utf-8")
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def run_xql_query(
    profile: CredentialProfile | str,
    *,
    query: str,
    timeframe: Optional[Mapping[str, Any]] = None,
    poll_interval_seconds: float = 1.5,
    max_poll_attempts: int = 120,
    stream_row_limit: int = 1000,
) -> dict[str, Any]:
    """Run an XQL query and return rows plus execution metadata."""
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    # Cortex API relativeTime is milliseconds (24h = 86_400_000).
    tf = dict(timeframe or {"relativeTime": 86_400_000})
    started_at = time.monotonic()
    query_id, start_status = api.start_xql_query(resolved, query=query, timeframe=tf)

    reply: dict[str, Any] = {}
    poll_status = start_status
    for _attempt in range(max_poll_attempts):
        reply, poll_status = api.get_query_results(resolved, query_id=query_id)
        status = str(reply.get("status") or "")
        if status == "PENDING":
            time.sleep(poll_interval_seconds)
            continue
        if status == "FAIL":
            raise RuntimeError(str(reply.get("err_msg") or "XQL query failed"))
        break
    else:
        raise TimeoutError(f"Timed out waiting for XQL query {query_id}")

    results = reply.get("results") if isinstance(reply.get("results"), dict) else {}
    expected = int(reply.get("number_of_results") or 0)
    rows: list[dict[str, Any]] = []

    inline_data = results.get("data") if isinstance(results, dict) else None
    if isinstance(inline_data, list) and inline_data and expected <= stream_row_limit:
        rows = [item for item in inline_data if isinstance(item, dict)]
    else:
        stream_id = results.get("stream_id") if isinstance(results, dict) else None
        if not stream_id:
            if isinstance(inline_data, list):
                rows = [item for item in inline_data if isinstance(item, dict)]
            else:
                raise RuntimeError("No inline data or stream_id in XQL results")
        else:
            raw = api.get_query_results_stream(resolved, stream_id=str(stream_id))
            rows = _parse_stream_rows(raw)

    elapsed_ms = int((time.monotonic() - started_at) * 1000)
    stream_id = results.get("stream_id") if isinstance(results, dict) else None
    return {
        "profile": resolved.slug,
        "query_id": query_id,
        "status": reply.get("status"),
        "number_of_results": expected or len(rows),
        "row_count": len(rows),
        "rows": rows,
        "elapsed_ms": elapsed_ms,
        "metrics": {
            "remaining_quota": reply.get("remaining_quota"),
            "query_cost": reply.get("query_cost_charged") or reply.get("query_cost"),
            "stream_id": stream_id,
            "err_msg": reply.get("err_msg"),
        },
        "status_codes": {
            "start": start_status,
            "poll": poll_status,
        },
    }
