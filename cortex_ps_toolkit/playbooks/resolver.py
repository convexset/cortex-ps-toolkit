"""Resolve and load playbooks from a tenant cache + live API."""

from __future__ import annotations

from typing import Any, Callable, Optional

ProgressCallback = Callable[[dict[str, Any]], None]

from ..credentials import CredentialProfile, get_profile
from ..ops_log import log_data_write, op_debug, op_info
from . import api
from .body_lookup import StalePolicy, lookup_playbook_body
from .cache import find_playbook_in_index, load_playbooks_index, save_playbook_body
from .yaml_helpers import playbook_identity, playbook_key


class CachePlaybookResolver:
    """Resolve sub-playbook references using cached index and live GET."""

    def __init__(
        self,
        profile: CredentialProfile | str,
        *,
        allow_live_fetch: bool = True,
        on_progress: Optional[ProgressCallback] = None,
        body_stale_policy: StalePolicy = "strict",
    ) -> None:
        self.profile = get_profile(profile) if isinstance(profile, str) else profile
        self.allow_live_fetch = allow_live_fetch
        self.on_progress = on_progress
        self.body_stale_policy = body_stale_policy
        self._by_id: dict[str, dict[str, Any]] = {}
        self._by_name: dict[str, dict[str, Any]] = {}
        self._loaded: dict[str, dict[str, Any]] = {}
        self._fetch_total: Optional[int] = None
        self._fetch_count = 0
        self.fetched_playbooks: list[dict[str, str]] = []
        self.restamped_playbooks: list[dict[str, str]] = []
        self._build_index()

    def set_fetch_total(self, total: int) -> None:
        self._fetch_total = max(0, int(total))

    def _emit_progress(self, event: dict[str, Any]) -> None:
        if self.on_progress:
            self.on_progress(event)

    def _remember_loaded(self, playbook: dict[str, Any], *keys: str) -> None:
        for raw in keys:
            key = str(raw or "").strip()
            if key:
                self._loaded[key] = playbook

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

    def load(
        self,
        playbook_id: str,
        *,
        allow_live_fetch: Optional[bool] = None,
        playbook_name: Optional[str] = None,
        body_stale_policy: Optional[StalePolicy] = None,
    ) -> dict[str, Any]:
        live_fetch = self.allow_live_fetch if allow_live_fetch is None else allow_live_fetch
        stale_policy = body_stale_policy or self.body_stale_policy
        lookup = lookup_playbook_body(
            self.profile,
            playbook_id=playbook_id,
            playbook_name=playbook_name,
            stale_policy=stale_policy,
            restamp_on_analysis_mismatch=True,
        )
        cache_key = lookup.canonical_id or playbook_id
        if cache_key in self._loaded:
            return self._loaded[cache_key]
        if lookup.status == "hit" and lookup.playbook is not None:
            cached = lookup.playbook
            if lookup.restamped_modified:
                self.restamped_playbooks.append(
                    {"id": lookup.canonical_id, "name": lookup.name},
                )
                op_info(
                    "CACHE playbook body %r (%s) — restamped index modified stamp",
                    lookup.name,
                    lookup.canonical_id,
                )
            else:
                op_debug(
                    "CACHE playbook body %r (%s) — local YAML",
                    lookup.name,
                    lookup.canonical_id,
                )
            pb_id, name = playbook_identity(cached)
            self._remember_loaded(cached, cache_key, pb_id, name, playbook_key(cached))
            if pb_id:
                self._by_id[pb_id] = {"id": pb_id, "name": name}
            if name:
                self._by_name[name] = {"id": pb_id, "name": name}
            return cached
        if not live_fetch:
            reason = lookup.status
            raise KeyError(
                f"Playbook body not cached: {playbook_id!r} on {self.profile.slug} "
                f"(reason={reason}; index lists metadata only until task YAML is downloaded)"
            )
        fetch_id = lookup.canonical_id or playbook_id
        meta = lookup.index_meta or self.meta(fetch_id) or {}
        display_name = str(meta.get("name") or lookup.name or fetch_id)
        self._fetch_count += 1
        self._emit_progress(
            {
                "phase": "fetch_playbook",
                "status": "running",
                "playbook_id": str(fetch_id),
                "playbook_name": display_name,
                "reason": lookup.status,
                "current": self._fetch_count,
                "total": self._fetch_total,
            },
        )
        playbook = api.get_playbook(self.profile, fetch_id)
        pb_id, pb_name = playbook_identity(playbook)
        store_id = str(pb_id or fetch_id)
        path = save_playbook_body(self.profile, store_id, playbook)
        log_data_write(
            "playbook body",
            detail=f"{pb_name or display_name} ({store_id}) → {path}",
        )
        self.fetched_playbooks.append({"id": store_id, "name": pb_name or display_name})
        self._emit_progress(
            {
                "phase": "fetch_playbook",
                "status": "complete",
                "playbook_id": store_id,
                "playbook_name": pb_name or display_name,
                "reason": lookup.status,
                "current": self._fetch_count,
                "total": self._fetch_total,
            },
        )
        pb_id, name = playbook_identity(playbook)
        if not pb_id:
            pb_id = store_id
        if not name:
            name = display_name
        self._remember_loaded(playbook, cache_key, store_id, pb_id, name, playbook_key(playbook))
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
