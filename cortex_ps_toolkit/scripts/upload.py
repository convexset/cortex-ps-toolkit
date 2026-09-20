"""Upload a script document to a tenant (copy or overwrite)."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ..content.yaml_codec import dumps_yaml
from ..core.paths import uses_cortex_platform_content_api
from ..credentials import CredentialProfile, get_profile
from ..platforms import Platform
from . import api
from .upload_prep import (
    prepare_script_for_save,
    script_to_xsiam_yaml_export,
    script_to_yaml_export,
)


def save_script_document(
    profile: CredentialProfile | str,
    script: Mapping[str, Any],
    *,
    filename: str,
    target_script_id: Optional[str] = None,
    overwrite: bool = False,
    target_name: Optional[str] = None,
) -> tuple[dict[str, Any], int]:
    """Upload script JSON with tenant-appropriate field preparation."""
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    prepared = prepare_script_for_save(
        script,
        target_script_id=target_script_id,
        overwrite=overwrite,
        target_name=target_name,
    )
    platform = resolved.tenant_type

    # XSOAR 8: JSON /automation preserves args and metadata reliably.
    if platform == Platform.XSOAR8:
        return api.save_script_json(resolved, prepared)

    # XSOAR 6 YAML import cannot update in place; JSON /automation is required for overwrite.
    if platform == Platform.XSOAR6 and overwrite:
        return api.save_script_json(resolved, prepared)

    if uses_cortex_platform_content_api(platform):
        yaml_source = script_to_xsiam_yaml_export(prepared)
    else:
        yaml_source = script_to_yaml_export(prepared)
    yaml_text = dumps_yaml(yaml_source)
    return api.save_script_yaml(resolved, yaml_text, filename=filename)
