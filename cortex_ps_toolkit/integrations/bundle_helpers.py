"""Integration definitions for bundle export and membership resolution."""

from __future__ import annotations

import copy
from typing import Any

from ..credentials import CredentialProfile, get_profile
from . import api
from .detail import _configuration_bodies, _lookup_body
from .metadata import integration_display_name, integration_key, is_copyable_integration
from .sanitize import sanitize_configuration_row


def get_configuration_for_bundle(
    profile: CredentialProfile | str,
    integration_id: str,
) -> dict[str, Any]:
    """Full ModuleConfiguration document for YAML export (script body included).

    Uses cached ``configuration_bodies`` when available. Do not use
    ``get_integration_definition_detail`` here — that splits ``integrationScript.script``
    out for the web viewer and breaks export eligibility + YAML content.
    """
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    cached = _lookup_body(_configuration_bodies(resolved), integration_id)
    if cached is None:
        document = api.find_integration_configuration(resolved, integration_id)
        cached = sanitize_configuration_row(document)
    return copy.deepcopy(cached)


def assert_exportable_integration(configuration: dict[str, Any]) -> None:
    copyable, reason = is_copyable_integration(configuration)
    if not copyable:
        name = integration_display_name(configuration)
        raise ValueError(reason or f"Integration {name!r} cannot be exported")


def bundle_member_id(configuration: dict[str, Any]) -> str:
    """Stable id for bundle items and copy (integration name key)."""
    return integration_key(configuration)
