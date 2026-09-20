"""Integration definition copy/delete eligibility."""

from __future__ import annotations

from typing import Any, Mapping, Optional


def integration_key(configuration: Mapping[str, Any]) -> str:
    return str(configuration.get("id") or configuration.get("name") or "")


def integration_display_name(configuration: Mapping[str, Any]) -> str:
    return str(configuration.get("display") or configuration.get("name") or integration_key(configuration))


def has_integration_script(configuration: Mapping[str, Any]) -> bool:
    script = configuration.get("integrationScript") or {}
    return bool(str(script.get("script") or "").strip())


def is_system_integration(configuration: Mapping[str, Any]) -> bool:
    return configuration.get("system") is True


def is_pack_integration(configuration: Mapping[str, Any]) -> bool:
    pack_id = configuration.get("packID") or configuration.get("packId")
    return bool(str(pack_id or "").strip())


def is_copyable_integration(configuration: Mapping[str, Any]) -> tuple[bool, Optional[str]]:
    name = integration_display_name(configuration)
    if is_system_integration(configuration):
        return False, f"System integration {name!r} cannot be copied"
    if is_pack_integration(configuration):
        return False, f"Content-pack integration {name!r} is not copied (install the pack on the target)"
    if not has_integration_script(configuration):
        return False, f"Integration {name!r} has no script body in integration/search (pack stub or unreadable)"
    return True, None


def is_deletable_integration(configuration: Mapping[str, Any]) -> tuple[bool, Optional[str]]:
    name = integration_display_name(configuration)
    if is_system_integration(configuration):
        return False, f"System integration {name!r} cannot be deleted"
    return True, None
