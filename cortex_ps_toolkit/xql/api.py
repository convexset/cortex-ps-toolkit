"""Low-level XQL HTTP calls."""

from __future__ import annotations

import time
from typing import Any, Mapping, Optional

from ..core.client import TenantClient
from ..credentials import CredentialProfile
from ..platforms import assert_operation_supported


def _client(profile: CredentialProfile) -> TenantClient:
    assert_operation_supported("xql.run", profile.tenant_type)
    return TenantClient(profile)


def start_xql_query(
    profile: CredentialProfile,
    *,
    query: str,
    timeframe: Mapping[str, Any],
) -> tuple[str, int]:
    client = _client(profile)
    payload = {
        "request_data": {
            "query": query,
            "timeframe": dict(timeframe),
        },
    }
    data, status = client.post_json_with_status(
        client.public_api_url("/xql/start_xql_query"),
        action="start XQL query",
        payload=payload,
    )
    if not isinstance(data, dict):
        raise ValueError(f"start_xql_query returned non-object: {type(data)}")
    query_id = data.get("reply")
    if not query_id:
        raise ValueError(f"start_xql_query missing reply: {data!r}")
    return str(query_id), status


def get_query_results(
    profile: CredentialProfile,
    *,
    query_id: str,
    limit: int = 1_000_000,
) -> tuple[dict[str, Any], int]:
    client = _client(profile)
    payload = {
        "request_data": {
            "query_id": query_id,
            "pending_flag": False,
            "limit": limit,
            "format": "json",
        },
    }
    data, status = client.post_json_with_status(
        client.public_api_url("/xql/get_query_results"),
        action="get XQL query results",
        payload=payload,
    )
    if not isinstance(data, dict):
        raise ValueError(f"get_query_results returned non-object: {type(data)}")
    reply = data.get("reply")
    if not isinstance(reply, dict):
        raise ValueError(f"get_query_results missing reply object: {data!r}")
    return reply, status


def get_query_results_stream(
    profile: CredentialProfile,
    *,
    stream_id: str,
    is_gzip_compressed: bool = False,
) -> bytes:
    client = _client(profile)
    payload = {
        "request_data": {
            "stream_id": stream_id,
            "is_gzip_compressed": is_gzip_compressed,
        },
    }
    return client.post_bytes(
        client.public_api_url("/xql/get_query_results_stream"),
        action="get XQL query results stream",
        payload=payload,
    )
