"""Automation script detail payloads for the web viewer."""

from __future__ import annotations

from typing import Any

from ..core.client import TenantApiError
from ..credentials import CredentialProfile, get_profile
from . import api


def split_script_document(document: dict[str, Any]) -> tuple[dict[str, Any], str]:
    doc = dict(document)
    script_text = str(doc.pop("script", "") or "")
    return doc, script_text


def get_script_detail(profile: CredentialProfile | str, script_id: str) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    needle = str(script_id)
    try:
        document = api.get_script(resolved, needle)
    except TenantApiError:
        document = api.get_script_by_name(resolved, needle)
    configuration, script_text = split_script_document(document)
    script_language = str(
        configuration.get("type")
        or configuration.get("language")
        or configuration.get("scriptType")
        or ""
    )
    return {
        "profile": resolved.slug,
        "id": str(configuration.get("id") or needle),
        "name": str(configuration.get("name") or ""),
        "kind": "script",
        "configuration": configuration,
        "script": script_text,
        "script_language": script_language,
    }
