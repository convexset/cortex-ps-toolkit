"""Same-tenant copy/update probes for copy-fidelity analysis."""

from __future__ import annotations

import copy
import uuid
from typing import Any, Optional

from ..core.client import TenantApiError
from ..credentials import CredentialProfile, get_profile
from ..lists.copy import resolve_list_entry
from ..lists.service import refresh_lists_cache, save_list
from ..playbooks import api as playbooks_api
from ..playbooks.service import refresh_playbooks_cache
from ..playbooks.upload import save_playbook_document
from ..scripts import api as scripts_api
from ..scripts.entity import script_entity_id
from ..scripts.service import refresh_scripts_cache
from ..scripts.upload import save_script_document
from .representation import diff_representations, normalize_representation


def _probe_name(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def _load_script_representation(profile: CredentialProfile, script_id: str) -> dict[str, Any]:
    return scripts_api.get_script(profile, script_id)


def _load_playbook_representation(profile: CredentialProfile, playbook_id: str) -> dict[str, Any]:
    return playbooks_api.get_playbook(profile, playbook_id)


def _load_list_representation(profile: CredentialProfile, list_id: str) -> dict[str, Any]:
    return resolve_list_entry(profile, list_id)


def _sample_docker_image(profile: CredentialProfile) -> str:
    refresh_scripts_cache(profile)
    from ..scripts.cache import load_scripts_index

    index = load_scripts_index(profile)
    for item in index.get("scripts") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        try:
            doc = scripts_api.get_script(profile, str(item["id"]))
        except Exception:
            continue
        docker = doc.get("dockerImage") or doc.get("dockerimage")
        if docker:
            return str(docker)
    return "demisto/python3:3.12.13.8428455"


def _create_probe_script(profile: CredentialProfile) -> tuple[str, dict[str, Any]]:
    name = _probe_name("CPTKScriptOw")
    marker = uuid.uuid4().hex[:8]
    doc = {
        "name": name,
        "script": (
            "def main():\n"
            f"    return_results('cptk-overwrite-probe-{marker}')\n"
        ),
        "type": "python",
        "subtype": "python3",
        "dockerImage": _sample_docker_image(profile),
        "enabled": True,
        "tags": [],
        "comment": f"CPTK overwrite probe {marker}",
    }
    filename = f"{name.replace('/', '_')}.yml"
    save_script_document(profile, doc, filename=filename)
    refresh_scripts_cache(profile)
    loaded = scripts_api.get_script_by_name(profile, name)
    script_id = script_entity_id(loaded)
    if not script_id:
        raise RuntimeError(f"Probe script {name!r} has no id after create on {profile.slug}")
    return script_id, loaded


def _create_probe_list(profile: CredentialProfile) -> tuple[str, dict[str, Any]]:
    name = _probe_name("CPTKListOw")
    marker = uuid.uuid4().hex[:8]
    data = f"cptk-overwrite-probe-{marker}"
    save_list(profile, name=name, data=data, list_type="plain_text", description="CPTK overwrite probe")
    refresh_lists_cache(profile)
    from ..lists.cache import find_list_in_index

    entry = find_list_in_index(profile, name=name)
    if not entry or not entry.get("id"):
        raise RuntimeError(f"Probe list {name!r} not found after create on {profile.slug}")
    list_id = str(entry["id"])
    return list_id, _load_list_representation(profile, list_id)


def _create_probe_playbook(profile: CredentialProfile) -> tuple[str, dict[str, Any]]:
    refresh_playbooks_cache(profile)
    from ..playbooks.cache import load_playbooks_index

    index = load_playbooks_index(profile)
    template_id = None
    for item in index.get("playbooks") or []:
        if isinstance(item, dict) and item.get("id") and not item.get("system"):
            template_id = str(item["id"])
            break
    if not template_id:
        for item in index.get("playbooks") or []:
            if isinstance(item, dict) and item.get("id"):
                template_id = str(item["id"])
                break
    if not template_id:
        raise RuntimeError(f"No playbook template available on {profile.slug}")

    template = playbooks_api.get_playbook(profile, template_id)
    name = _probe_name("CPTKPBOw")
    doc = copy.deepcopy(template)
    doc["name"] = name
    filename = f"{name.replace('/', '_')}.yml"
    try:
        save_playbook_document(profile, doc, filename=filename)
    except TenantApiError:
        # Retry once in case a prior probe left a partial insert.
        refresh_playbooks_cache(profile)
        existing = playbooks_api.get_playbook_by_name(profile, name)
        if existing:
            return str(existing.get("id") or ""), existing
        raise
    refresh_playbooks_cache(profile)
    loaded = playbooks_api.get_playbook_by_name(profile, name)
    playbook_id = str(loaded.get("id") or "")
    if not playbook_id:
        raise RuntimeError(f"Probe playbook {name!r} has no id after create on {profile.slug}")
    return playbook_id, loaded


def _cleanup_script(profile: CredentialProfile, script_id: str) -> None:
    if not script_id:
        return
    try:
        scripts_api.delete_script(profile, script_id=script_id)
        refresh_scripts_cache(profile)
    except Exception:
        pass


def _cleanup_list(profile: CredentialProfile, list_id: str) -> None:
    if not list_id:
        return
    try:
        from ..lists import api as lists_api

        lists_api.delete_list_by_id(profile, list_id)
        refresh_lists_cache(profile)
    except Exception:
        pass


def _cleanup_playbook(profile: CredentialProfile, playbook_id: str) -> None:
    if not playbook_id:
        return
    try:
        playbooks_api.delete_playbook(profile, playbook_id=playbook_id)
        refresh_playbooks_cache(profile)
    except Exception:
        pass


def probe_script_copy_fidelity(
    profile: str | CredentialProfile,
    script_id: str,
    *,
    target_name: Optional[str] = None,
    cleanup: bool = True,
) -> dict[str, Any]:
    """Refresh → snapshot → renamed same-tenant copy → refresh → diff."""
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    refresh_scripts_cache(resolved)
    source_doc = _load_script_representation(resolved, script_id)
    copy_name = target_name or _probe_name("CPTKScriptProbe")
    filename = f"{copy_name.replace('/', '_')}.yml"

    save_script_document(
        resolved,
        source_doc,
        filename=filename,
        target_name=copy_name,
    )
    refresh_scripts_cache(resolved)
    copied_doc = scripts_api.get_script_by_name(resolved, copy_name)
    diff = diff_representations(source_doc, copied_doc, "script")

    copied_id = script_entity_id(copied_doc)
    if cleanup and copied_id:
        _cleanup_script(resolved, copied_id)

    return _probe_result("script", resolved.slug, source_doc, copied_doc, script_id, copy_name, copied_id, diff)


def probe_script_overwrite_fidelity(
    profile: str | CredentialProfile,
    *,
    cleanup: bool = True,
) -> dict[str, Any]:
    """Create probe script → snapshot → in-place overwrite → refresh → diff."""
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    script_id, before_doc = _create_probe_script(resolved)
    filename = f"{before_doc.get('name', 'script')}.yml".replace("/", "_")

    try:
        save_script_document(
            resolved,
            before_doc,
            filename=filename,
            target_script_id=script_id,
            overwrite=True,
        )
    except TenantApiError as exc:
        if cleanup:
            _cleanup_script(resolved, script_id)
        return {
            "kind": "script",
            "mode": "overwrite",
            "profile": resolved.slug,
            "source_id": script_id,
            "error": str(exc),
            "response": exc.body if isinstance(exc.body, dict) else {},
            "diff": {"equal": False, "differences": [{"path": "_save", "error": str(exc)}]},
        }

    refresh_scripts_cache(resolved)
    after_doc = _load_script_representation(resolved, script_id)
    diff = diff_representations(before_doc, after_doc, "script")
    if cleanup:
        _cleanup_script(resolved, script_id)

    return _probe_result(
        "script",
        resolved.slug,
        before_doc,
        after_doc,
        script_id,
        str(before_doc.get("name") or ""),
        script_id,
        diff,
        mode="overwrite",
    )


def probe_playbook_copy_fidelity(
    profile: str | CredentialProfile,
    playbook_id: str,
    *,
    target_name: Optional[str] = None,
    cleanup: bool = True,
) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    refresh_playbooks_cache(resolved)
    source_doc = _load_playbook_representation(resolved, playbook_id)
    copy_name = target_name or _probe_name("CPTKPlaybookProbe")
    playbook_copy = dict(source_doc)
    playbook_copy["name"] = copy_name
    filename = f"{copy_name.replace('/', '_')}.yml"

    try:
        save_playbook_document(resolved, playbook_copy, filename=filename)
    except TenantApiError as exc:
        return {
            "kind": "playbook",
            "mode": "copy",
            "profile": resolved.slug,
            "source_id": playbook_id,
            "source_name": source_doc.get("name"),
            "copy_name": copy_name,
            "error": str(exc),
            "response": exc.body if isinstance(exc.body, dict) else {},
            "diff": {"equal": False, "differences": [{"path": "_save", "error": str(exc)}]},
        }
    refresh_playbooks_cache(resolved)
    copied_doc = playbooks_api.get_playbook_by_name(resolved, copy_name)
    diff = diff_representations(source_doc, copied_doc, "playbook")

    copied_id = str(copied_doc.get("id") or "")
    if cleanup and copied_id:
        _cleanup_playbook(resolved, copied_id)

    return _probe_result("playbook", resolved.slug, source_doc, copied_doc, playbook_id, copy_name, copied_id, diff)


def probe_playbook_overwrite_fidelity(
    profile: str | CredentialProfile,
    *,
    cleanup: bool = True,
) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    playbook_id, before_doc = _create_probe_playbook(resolved)
    name = str(before_doc.get("name") or "")
    filename = f"{name.replace('/', '_')}.yml"

    try:
        save_playbook_document(
            resolved,
            before_doc,
            filename=filename,
            target_playbook_id=playbook_id,
            overwrite=True,
        )
    except TenantApiError as exc:
        if cleanup:
            _cleanup_playbook(resolved, playbook_id)
        return {
            "kind": "playbook",
            "mode": "overwrite",
            "profile": resolved.slug,
            "source_id": playbook_id,
            "error": str(exc),
            "response": exc.body if isinstance(exc.body, dict) else {},
            "diff": {"equal": False, "differences": [{"path": "_save", "error": str(exc)}]},
        }

    refresh_playbooks_cache(resolved)
    after_doc = _load_playbook_representation(resolved, playbook_id)
    diff = diff_representations(before_doc, after_doc, "playbook")
    if cleanup:
        _cleanup_playbook(resolved, playbook_id)

    return _probe_result(
        "playbook",
        resolved.slug,
        before_doc,
        after_doc,
        playbook_id,
        name,
        playbook_id,
        diff,
        mode="overwrite",
    )


def probe_list_copy_fidelity(
    profile: str | CredentialProfile,
    list_id: str,
    *,
    target_name: Optional[str] = None,
    cleanup: bool = True,
) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    refresh_lists_cache(resolved)
    source_doc = _load_list_representation(resolved, list_id)
    copy_name = target_name or _probe_name("CPTKListProbe")

    save_list(
        resolved,
        name=copy_name,
        data=str(source_doc.get("data") or ""),
        list_type=str(source_doc.get("type") or "plain_text"),
        description=str(source_doc.get("description") or ""),
    )
    refresh_lists_cache(resolved)
    from ..lists.cache import find_list_in_index

    copied_index = find_list_in_index(resolved, name=copy_name)
    if not copied_index:
        raise KeyError(f"Copied list {copy_name!r} not found after save")
    copied_doc = _load_list_representation(resolved, str(copied_index["id"]))
    diff = diff_representations(source_doc, copied_doc, "list")

    copied_id = str(copied_index.get("id") or "")
    if cleanup and copied_id:
        _cleanup_list(resolved, copied_id)

    return _probe_result("list", resolved.slug, source_doc, copied_doc, list_id, copy_name, copied_id, diff)


def probe_list_overwrite_fidelity(
    profile: str | CredentialProfile,
    *,
    cleanup: bool = True,
) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    list_id, before_doc = _create_probe_list(resolved)
    name = str(before_doc.get("name") or "")

    save_list(
        resolved,
        name=name,
        data=str(before_doc.get("data") or ""),
        list_type=str(before_doc.get("type") or "plain_text"),
        description=str(before_doc.get("description") or ""),
        list_id=list_id,
    )
    refresh_lists_cache(resolved)
    after_doc = _load_list_representation(resolved, list_id)
    diff = diff_representations(before_doc, after_doc, "list")
    if cleanup:
        _cleanup_list(resolved, list_id)

    return _probe_result(
        "list",
        resolved.slug,
        before_doc,
        after_doc,
        list_id,
        name,
        list_id,
        diff,
        mode="overwrite",
    )


def _probe_result(
    kind: str,
    profile: str,
    source_doc: dict[str, Any],
    copied_doc: dict[str, Any],
    source_id: str,
    copy_name: str,
    copy_id: str | None,
    diff: Any,
    *,
    mode: str = "copy",
) -> dict[str, Any]:
    return {
        "kind": kind,
        "mode": mode,
        "profile": profile,
        "source_id": source_id,
        "source_name": source_doc.get("name"),
        "copy_name": copy_name,
        "copy_id": copy_id or None,
        "source_representation": normalize_representation(source_doc, kind),  # type: ignore[arg-type]
        "copy_representation": normalize_representation(copied_doc, kind),  # type: ignore[arg-type]
        "diff": diff.to_dict(),
    }


def assert_fidelity_equal(result: dict[str, Any], *, max_report: int = 5) -> None:
    if result.get("error"):
        raise AssertionError(
            f"{result.get('kind')} {result.get('mode', 'copy')} failed on {result.get('profile')}: "
            f"{result['error']}"
        )
    diff = result.get("diff") or {}
    if diff.get("equal"):
        return
    differences = diff.get("differences") or []
    sample = differences[:max_report]
    raise AssertionError(
        f"{result.get('kind')} {result.get('mode', 'copy')} fidelity mismatch on {result.get('profile')}: "
        f"{len(differences)} difference(s); sample={sample}"
    )
