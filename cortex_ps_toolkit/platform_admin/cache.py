"""On-disk cache for platform admin listings."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ..credentials import CredentialProfile
from ..paths import cache_root
from .types import AdminSection


def admin_cache_dir(profile: CredentialProfile) -> Path:
    return cache_root() / profile.cache_key / "platform_admin"


def index_path(profile: CredentialProfile, section: AdminSection) -> Path:
    return admin_cache_dir(profile) / section / "index.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_index(profile: CredentialProfile, section: AdminSection) -> dict[str, Any]:
    path = index_path(profile, section)
    if not path.exists():
        return {"version": 1, "section": section, "refreshed_at": None, "items": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Platform admin index must be object: {path}")
    return payload


def write_cache(profile: CredentialProfile, section: AdminSection, items: list[dict[str, Any]]) -> Path:
    path = index_path(profile, section)
    path.parent.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        user_email = item.get("user_email") or item.get("email")
        full_name = " ".join(
            part for part in (item.get("user_first_name"), item.get("user_last_name")) if part
        ).strip()
        summary = {
            "id": (
                item.get("id")
                or item.get("rule_id")
                or user_email
                or item.get("key_id")
                or item.get("group_name")
                or item.get("pretty_name")
                or item.get("name")
                or item.get("indicator_id")
            ),
            "name": (
                item.get("name")
                or full_name
                or item.get("pretty_name")
                or item.get("group_name")
                or item.get("alert_name")
                or user_email
                or item.get("comment")
                or item.get("value")
                or item.get("indicator")
            ),
        }
        for key in ("type", "role", "role_name", "user_email", "key_id", "indicator_type", "module", "user_type"):
            if key in item:
                summary[key] = item[key]
        if section == "rbac-users":
            summary["user_email"] = user_email or summary.get("user_email")
            summary["id"] = user_email or summary.get("id")
            summary["name"] = full_name or item.get("role_name") or user_email or summary.get("name")
            summary["role"] = item.get("role_name") or item.get("role") or summary.get("role")
        elif section == "rbac-roles":
            summary["id"] = item.get("pretty_name") or summary.get("id")
            summary["name"] = item.get("pretty_name") or item.get("description") or summary.get("name")
        elif section == "rbac-groups":
            summary["id"] = item.get("group_name") or summary.get("id")
            summary["name"] = item.get("pretty_name") or item.get("group_name") or summary.get("name")
        elif section == "api-keys":
            summary["id"] = str(item.get("id") or item.get("key_id") or summary.get("id") or "")
            summary["key_id"] = item.get("id") or item.get("key_id") or summary.get("key_id")
            summary["name"] = item.get("comment") or item.get("user_name") or summary.get("name")
            roles = item.get("roles")
            if roles and not summary.get("role"):
                summary["role"] = ", ".join(str(role) for role in roles) if isinstance(roles, list) else str(roles)
            for key in ("created_by", "creation_time", "expiration", "security_level", "user_name"):
                if key in item:
                    summary[key] = item[key]
        elif section == "indicators" and not summary.get("type"):
            summary["type"] = item.get("indicator_type") or item.get("module") or item.get("type")
        summaries.append(summary)
    payload = {
        "version": 1,
        "section": section,
        "profile_slug": profile.slug,
        "cache_key": profile.cache_key,
        "refreshed_at": _utc_now_iso(),
        "count": len(summaries),
        "items": summaries,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def list_cached(profile: CredentialProfile, section: AdminSection) -> list[dict[str, Any]]:
    index = load_index(profile, section)
    return [item for item in (index.get("items") or []) if isinstance(item, dict)]
