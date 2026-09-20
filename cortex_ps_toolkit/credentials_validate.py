"""Validate credential profiles against live tenants."""

from __future__ import annotations

from typing import Any

from .system.validate import run_credential_validation


def validate_profile(slug_or_id: str) -> dict[str, Any]:
    """Validate credentials using platform system-management endpoints."""
    return run_credential_validation(slug_or_id)
