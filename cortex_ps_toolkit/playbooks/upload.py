"""Upload a playbook document to a tenant (copy or overwrite)."""

from __future__ import annotations

import copy
from typing import Any, Mapping, Optional

from ..content.yaml_codec import dumps_yaml
from ..credentials import CredentialProfile, get_profile
from . import api
from .cache import playbook_body_path
from .upload_prep import prepare_playbook_for_save
from .yaml_bindings import prepare_playbook_bindings_for_upload
from .yaml_export import rename_playbook_keys_for_yaml


def save_playbook_document(
    profile: CredentialProfile | str,
    playbook: Mapping[str, Any],
    *,
    filename: str,
    target_playbook_id: Optional[str] = None,
    overwrite: bool = False,
    source_profile: Optional[CredentialProfile | str] = None,
    playbook_name_to_id: Optional[Mapping[str, str]] = None,
    playbook_id_to_name: Optional[Mapping[str, str]] = None,
    script_id_remap: Optional[Mapping[str, str]] = None,
    playbook_id_remap: Optional[Mapping[str, str]] = None,
) -> tuple[dict[str, Any], int, list[dict[str, Any]]]:
    """Upload playbook JSON; returns ``(response, status_code, unresolved_bindings)``."""
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    prepared = prepare_playbook_for_save(
        playbook,
        target_playbook_id=target_playbook_id,
        overwrite=overwrite,
    )
    upload_doc = copy.deepcopy(prepared)

    unresolved = prepare_playbook_bindings_for_upload(
        upload_doc,
        resolved,
        source_profile=source_profile,
        playbook_name_to_id=playbook_name_to_id,
        playbook_id_to_name=playbook_id_to_name,
        script_id_remap=script_id_remap,
        playbook_id_remap=playbook_id_remap,
    )

    yaml_ready = rename_playbook_keys_for_yaml(upload_doc)
    yaml_text = dumps_yaml(yaml_ready)
    saved, status_code = api.save_playbook_yaml(resolved, yaml_text, filename=filename)
    if overwrite and target_playbook_id:
        body_path = playbook_body_path(resolved, target_playbook_id)
        if body_path.exists():
            body_path.unlink()
    return saved, status_code, unresolved
