"""Resolve and load playbooks from a tenant cache + live API."""

from __future__ import annotations

from typing import Any, Optional

from ..credentials import CredentialProfile, get_profile
from . import api
from .cache import find_playbook_in_index, load_playbook_body, load_playbooks_index, save_playbook_body
from .yaml_helpers import playbook_identity


class CachePlaybookResolver:
    """Resolve sub-playbook references using cached index and live GET."""

    def __init__(self, profile: CredentialProfile | str) -> None:
        self.profile = get_profile(profile) if isinstance(profile, str) else profile
        self._by_id: dict[str, dict[str, Any]] = {}
        self._by_name: dict[str, dict[str, Any]] = {}
        self._loaded: dict[str, dict[str, Any]] = {}
        self._build_index()

    def _build_index(self) -> None:
        index = load_playbooks_index(self.profile)
        for item in index.get("playbooks") or []:
            if not isinstance(item, dict):
                continue
            pb_id = str(item.get("id") or "")
            name = str(item.get("name") or "")
            if pb_id:
                self._by_id[pb_id] = item
            if name:
                self._by_name[name] = item

    def resolve(self, playbook_id: Optional[str], playbook_name: Optional[str]) -> Optional[str]:
        if playbook_id and playbook_id in self._by_id:
            return playbook_id
        if playbook_name and playbook_name in self._by_name:
            return str(self._by_name[playbook_name].get("id") or "")
        if playbook_id and playbook_id in self._by_name:
            return str(self._by_name[playbook_id].get("id") or "")
        if playbook_name and playbook_name in self._by_id:
            return playbook_name
        return None

    def meta(self, playbook_id: str) -> Optional[dict[str, Any]]:
        return self._by_id.get(playbook_id) or find_playbook_in_index(self.profile, playbook_id=playbook_id)

    def load(self, playbook_id: str, *, allow_live_fetch: bool = True) -> dict[str, Any]:
        if playbook_id in self._loaded:
            return self._loaded[playbook_id]
        cached = load_playbook_body(self.profile, playbook_id)
        if cached is not None:
            self._loaded[playbook_id] = cached
            pb_id, name = playbook_identity(cached)
            if pb_id:
                self._by_id[pb_id] = {"id": pb_id, "name": name}
            if name:
                self._by_name[name] = {"id": pb_id, "name": name}
            return cached
        if not allow_live_fetch:
            raise KeyError(f"Playbook body not cached: {playbook_id!r} on {self.profile.slug}")
        playbook = api.get_playbook(self.profile, playbook_id)
        save_playbook_body(self.profile, playbook_id, playbook)
        self._loaded[playbook_id] = playbook
        pb_id, name = playbook_identity(playbook)
        if pb_id:
            self._by_id[pb_id] = {"id": pb_id, "name": name}
        if name:
            self._by_name[name] = {"id": pb_id, "name": name}
        return playbook

    def name_to_id(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for name, item in self._by_name.items():
            pb_id = str(item.get("id") or "")
            if pb_id:
                mapping[name] = pb_id
        return mapping

    def id_to_name(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for pb_id, item in self._by_id.items():
            name = str(item.get("name") or "")
            if name:
                mapping[pb_id] = name
        return mapping

    def load_by_key(self, key: str) -> dict[str, Any]:
        if key in self._loaded:
            return self._loaded[key]
        if key in self._by_id:
            return self.load(key)
        if key in self._by_name:
            return self.load(str(self._by_name[key].get("id") or key))
        return self.load(key)
