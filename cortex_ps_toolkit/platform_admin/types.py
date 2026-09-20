"""Platform admin section identifiers."""

from __future__ import annotations

from typing import Literal

AdminSection = Literal[
    "correlation-rules",
    "biocs",
    "indicators",
    "rbac-users",
    "rbac-roles",
    "rbac-groups",
    "api-keys",
]

ADMIN_SECTIONS: tuple[AdminSection, ...] = (
    "correlation-rules",
    "biocs",
    "indicators",
    "rbac-users",
    "rbac-roles",
    "rbac-groups",
    "api-keys",
)

OPERATION_BY_SECTION: dict[AdminSection, str] = {
    "correlation-rules": "content.correlation_rules.list",
    "biocs": "content.biocs.manage",
    "indicators": "content.indicators.manage",
    "rbac-users": "system.rbac.read",
    "rbac-roles": "system.rbac.read",
    "rbac-groups": "system.rbac.read",
    "api-keys": "system.api_keys.manage",
}
