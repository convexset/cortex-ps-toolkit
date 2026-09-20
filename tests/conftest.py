"""Shared pytest fixtures for cortex-ps-toolkit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import pytest

from cortex_ps_toolkit.credentials import get_profile, list_profiles
from cortex_ps_toolkit.platforms import Platform, parse_platform

# Lab tenants with credentials on disk (see presets/credentials/lab-sources.json).
# XDR 3 is intentionally excluded — no lab tenant available.
LAB_TENANT_CASES: tuple[tuple[str, Platform], ...] = (
    ("personal-xsoar6", Platform.XSOAR6),
    ("xsoar-japac-dev", Platform.XSOAR8),
    ("psojapac-xsiam", Platform.XSIAM),
    ("cortex-cs-xdr5", Platform.XDR5),
    ("cortex-cs-agentix", Platform.AGENTIX),
)

LAB_TENANT_SLUGS: tuple[str, ...] = tuple(slug for slug, _ in LAB_TENANT_CASES)
LAB_TENANT_BY_SLUG: dict[str, Platform] = dict(LAB_TENANT_CASES)


@dataclass(frozen=True)
class LabTenant:
    slug: str
    platform: Platform


def _lab_tenant(slug: str, platform: Platform) -> LabTenant:
    profile = get_profile(slug)
    if profile.tenant_type != platform:
        pytest.fail(
            f"Profile {slug!r} is {profile.tenant_type.value}, expected {platform.value}",
        )
    return LabTenant(slug=slug, platform=platform)


@pytest.fixture(scope="session")
def available_lab_slugs() -> set[str]:
    return {profile.slug for profile in list_profiles()}


@pytest.fixture(params=LAB_TENANT_CASES, ids=[slug for slug, _ in LAB_TENANT_CASES])
def lab_tenant(request: pytest.FixtureRequest, available_lab_slugs: set[str]) -> Iterator[LabTenant]:
    slug, platform = request.param
    if slug not in available_lab_slugs:
        pytest.skip(f"Lab credential profile {slug!r} is not configured on this machine")
    yield _lab_tenant(slug, platform)
