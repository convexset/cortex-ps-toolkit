"""Profile-scoped capability flags for content management UI."""

from __future__ import annotations

from typing import Any

from .credentials import CredentialProfile, get_profile
from .design_content.delete import _delete_supported
from .design_content.types import ASSET_KINDS, OPERATION_BY_ASSET
from .platform_admin.types import ADMIN_SECTIONS, OPERATION_BY_SECTION
from .platforms import SupportLevel, get_operation


def _level(profile: CredentialProfile, operation_id: str) -> str:
    spec = get_operation(operation_id)
    level = spec.support_level(profile.tenant_type)
    if level == SupportLevel.DOCUMENTED:
        return "documented"
    if level == SupportLevel.EXPERIMENTAL:
        return "experimental"
    return "unsupported"


def profile_capabilities(profile: CredentialProfile | str) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    platform = resolved.tenant_type.value

    object_setup: dict[str, Any] = {}
    for asset in ASSET_KINDS:
        op = OPERATION_BY_ASSET[asset]
        object_setup[asset] = {
            "list": _level(resolved, op) != "unsupported",
            "copy": _level(resolved, op) != "unsupported",
            "delete": _delete_supported(resolved, asset),
            "support": _level(resolved, op),
        }

    correlation_op = OPERATION_BY_SECTION["correlation-rules"]
    object_setup["correlation-rules"] = {
        "list": _level(resolved, correlation_op) != "unsupported",
        "copy": _level(resolved, correlation_op) != "unsupported",
        "delete": _level(resolved, correlation_op) != "unsupported",
        "support": _level(resolved, correlation_op),
    }

    indicators: dict[str, Any] = {}
    for section in ("indicators", "biocs"):
        op = OPERATION_BY_SECTION[section]
        supported = _level(resolved, op) != "unsupported"
        indicators[section] = {
            "list": supported,
            "copy": supported,
            "delete": supported,
            "support": _level(resolved, op),
        }

    system_admin: dict[str, Any] = {}
    for section in ("rbac-users", "rbac-roles", "rbac-groups", "api-keys"):
        op = OPERATION_BY_SECTION[section]
        system_admin[section] = {
            "list": _level(resolved, op) != "unsupported",
            "copy": False,
            "delete": section == "api-keys" and _level(resolved, op) != "unsupported",
            "generate": section == "api-keys" and _level(resolved, op) != "unsupported",
            "support": _level(resolved, op),
        }

    return {
        "profile": resolved.slug,
        "platform": platform,
        "object_setup": object_setup,
        "indicators": indicators,
        "system_admin": system_admin,
    }
