"""On-disk playbook cache with TTL and upload invalidation."""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence

from .client import PlaybookApiError, PlaybookClient
from .operation_log import timed_operation
from .credentials import Credentials, Platform
from .keys import JsonDict, normalize_playbook, playbook_tasks, start_task_id


DEFAULT_TTL_SECONDS = 3600


@dataclass
class CacheMeta:
    url: str
    platform: str
    fetched_at: float
    ttl_seconds: float
    playbook_count: int
    complete: bool = True

    def to_dict(self) -> JsonDict:
        return {
            "url": self.url,
            "platform": self.platform,
            "fetched_at": self.fetched_at,
            "ttl_seconds": self.ttl_seconds,
            "playbook_count": self.playbook_count,
            "complete": self.complete,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CacheMeta":
        return cls(
            url=str(data.get("url") or ""),
            platform=str(data.get("platform") or ""),
            fetched_at=float(data.get("fetched_at") or 0),
            ttl_seconds=float(data.get("ttl_seconds") or DEFAULT_TTL_SECONDS),
            playbook_count=int(data.get("playbook_count") or 0),
            complete=bool(data.get("complete", True)),
        )

    def is_fresh(self, now: Optional[float] = None) -> bool:
        if not self.complete:
            return False
        current = time.time() if now is None else now
        if self.ttl_seconds <= 0:
            return True
        return (current - self.fetched_at) < self.ttl_seconds

    def age_seconds(self, now: Optional[float] = None) -> float:
        current = time.time() if now is None else now
        return max(0.0, current - self.fetched_at)


def playbook_summary(playbook: Mapping[str, Any]) -> JsonDict:
    tasks = playbook_tasks(playbook)
    tags = playbook.get("tags") or []
    if not isinstance(tags, list):
        tags = [tags]
    return {
        "id": str(playbook.get("id") or ""),
        "name": str(playbook.get("name") or ""),
        "version": playbook.get("version"),
        "modified": playbook.get("modified"),
        "created": playbook.get("created"),
        "task_count": len(tasks),
        "startTaskId": start_task_id(playbook),
        "tags": tags,
        "packName": playbook.get("packName"),
        "deprecated": playbook.get("deprecated"),
        "hidden": playbook.get("hidden"),
    }


def format_manifest_text(manifest: Mapping[str, Any]) -> str:
    tenant = manifest.get("tenant") or {}
    lines = [
        f"Tenant URL:   {tenant.get('url')}",
        f"Tenant type:  {tenant.get('tenant_type')}",
        f"Cache dir:    {manifest.get('cache_dir')}",
        f"Fetched at:   {manifest.get('fetched_at')}",
        f"Complete:     {manifest.get('complete')}",
        f"Playbooks:    {manifest.get('count')}",
        "",
        f"{'ID':<40} {'TASKS':>5} {'VER':>4}  NAME",
        f"{'-'*40} {'-'*5} {'-'*4}  {'-'*40}",
    ]
    for row in manifest.get("playbooks") or []:
        pid = str(row.get("id") or "")[:40]
        tasks = str(row.get("task_count") if row.get("task_count") is not None else "")
        ver = str(row.get("version") if row.get("version") is not None else "")
        name = str(row.get("name") or "")
        lines.append(f"{pid:<40} {tasks:>5} {ver:>4}  {name}")
    return "\n".join(lines)


def isoformat_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PlaybookCache:
    def __init__(
        self,
        credentials: Credentials,
        client: PlaybookClient,
        cache_dir: Path,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ):
        self.credentials = credentials
        self.client = client
        self.ttl_seconds = ttl_seconds
        self.root = Path(cache_dir) / credentials.cache_key
        self.playbooks_dir = self.root / "playbooks"
        self.meta_path = self.root / "meta.json"
        self.index_path = self.root / "index.json"

    def meta(self) -> Optional[CacheMeta]:
        if not self.meta_path.exists():
            return None
        try:
            data = json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        return CacheMeta.from_dict(data)

    def is_fresh(self) -> bool:
        meta = self.meta()
        return bool(meta and meta.is_fresh())

    def invalidate(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)

    def mark_stale(self) -> None:
        """Drop freshness metadata but keep cached playbooks for concurrent readers."""
        if self.meta_path.exists():
            self.meta_path.unlink()

    def status(self) -> JsonDict:
        meta = self.meta()
        index = self._load_index()
        return {
            "cache_dir": str(self.root),
            "fresh": self.is_fresh(),
            "exists": meta is not None,
            "meta": meta.to_dict() if meta else None,
            "age_seconds": meta.age_seconds() if meta else None,
            "indexed_playbooks": len(index.get("by_id") or {}),
        }

    def refresh(self, *, query: Optional[str] = None) -> List[JsonDict]:
        with timed_operation("Refresh playbook cache"):
            payload = self.client.search_playbooks(query=query)
            playbooks = [
                normalize_playbook(item)
                for item in (payload.get("playbooks") or [])
                if isinstance(item, dict)
            ]
            self._write_all(playbooks, complete=True)
            return playbooks

    def redownload_after_save(self, *, playbook_id: Optional[str] = None, name: str) -> JsonDict:
        """Reload a just-saved playbook in the same document family as the cache.

        XSOAR 6/8: GET JSON by id (same shape as search).
        XSIAM: bulk search refresh, then resolve by name — search JSON vs search JSON,
        not the YAML ZIP from ``/playbooks/get``.
        """
        if self.credentials.platform == Platform.XSIAM:
            self.refresh()
            return self.resolve(name, force=False)
        if playbook_id:
            return self.get(playbook_id, force=True)
        self.refresh()
        return self.resolve(name, force=False)

    def ensure(self, *, force: bool = False, query: Optional[str] = None) -> List[JsonDict]:
        if force or not self.is_fresh():
            return self.refresh(query=query)
        return self._load_all()

    def list_summaries(self, *, force: bool = False) -> List[JsonDict]:
        self.ensure(force=force)
        return self._summaries_from_index()

    def _summaries_from_index(self) -> List[JsonDict]:
        index = self._load_index()
        summaries = []
        for pid, info in (index.get("by_id") or {}).items():
            if isinstance(info, dict) and "task_count" in info:
                row = dict(info)
                row.setdefault("id", pid)
                summaries.append(row)
            else:
                summaries.append({"id": pid, "name": (info or {}).get("name") if isinstance(info, dict) else ""})
        summaries.sort(key=lambda row: (str(row.get("name") or "").lower(), str(row.get("id") or "")))
        return summaries

    def build_manifest(self) -> JsonDict:
        meta = self.meta()
        playbooks = self._summaries_from_index()
        fetched_at = isoformat_now()
        if meta:
            fetched_at = datetime.fromtimestamp(meta.fetched_at, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "tenant": {
                "url": self.credentials.url,
                "host": self.credentials.host,
                "tenant_type": self.credentials.platform.value,
            },
            "cache_dir": str(self.root),
            "fetched_at": fetched_at,
            "complete": bool(meta.complete) if meta else False,
            "count": len(playbooks),
            "playbooks": playbooks,
        }

    def write_manifest(self) -> JsonDict:
        manifest = self.build_manifest()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
        (self.root / "manifest.txt").write_text(format_manifest_text(manifest) + "\n", encoding="utf-8")
        return manifest

    def get(self, playbook_id: str, *, force: bool = False) -> JsonDict:
        if not force:
            cached = self._read_playbook(playbook_id)
            if cached is not None and (self.is_fresh() or self.credentials.platform == Platform.XSIAM):
                return cached
        playbook = self._fetch_live(playbook_id)
        self._upsert(playbook)
        return playbook

    def _fetch_live(self, name_or_id: str) -> JsonDict:
        try:
            return normalize_playbook(self.client.get_playbook(name_or_id))
        except PlaybookApiError:
            if self.credentials.platform == Platform.XSIAM:
                return normalize_playbook(self.client.get_playbook_by_name(name_or_id))
            raise

    def resolve_index_only(self, name_or_id: str) -> JsonDict:
        """Resolve id and name from the on-disk index only (no tenant GET or refresh)."""
        index = self._load_index()
        by_id = index.get("by_id") or {}
        if name_or_id in by_id:
            row = by_id[name_or_id]
            if isinstance(row, dict):
                return {"id": name_or_id, "name": str(row.get("name") or "")}
            return {"id": name_or_id, "name": ""}
        matches = (index.get("by_name") or {}).get(name_or_id) or []
        if len(matches) == 1:
            pid = str(matches[0])
            row = by_id.get(pid) or {}
            name = str(row.get("name") or name_or_id) if isinstance(row, dict) else name_or_id
            return {"id": pid, "name": name}
        if len(matches) > 1:
            raise KeyError(f"Playbook name {name_or_id!r} is ambiguous: {matches}")
        raise KeyError(f"Playbook {name_or_id!r} not found in local index")

    def resolve(self, name_or_id: str, *, force: bool = False) -> JsonDict:
        """Resolve a playbook by id or unique name from the cache, then live API."""
        if self.credentials.platform.supports_bulk_search():
            self.ensure(force=False)
        index = self._load_index()
        by_id = index.get("by_id") or {}
        if name_or_id in by_id and not force:
            return self.get(name_or_id, force=False)
        matches = (index.get("by_name") or {}).get(name_or_id) or []
        if len(matches) == 1 and not force:
            return self.get(matches[0], force=False)
        if len(matches) > 1:
            raise KeyError(f"Playbook name {name_or_id!r} is ambiguous: {matches}")
        try:
            playbook = self._fetch_live(name_or_id)
            self._upsert(playbook)
            return playbook
        except PlaybookApiError:
            pass
        if self.credentials.platform.supports_bulk_search():
            self.refresh()
            index = self._load_index()
            if name_or_id in (index.get("by_id") or {}):
                return self.get(name_or_id)
            matches = (index.get("by_name") or {}).get(name_or_id) or []
            if len(matches) == 1:
                return self.get(matches[0])
        raise KeyError(f"Playbook {name_or_id!r} not found by id or name")

    def find_by_name_prefix(self, prefix: str, *, force: bool = False) -> List[JsonDict]:
        """Return cached summaries whose name starts with ``prefix`` (case-sensitive)."""
        return [
            row
            for row in self.list_summaries(force=force)
            if str(row.get("name") or "").startswith(prefix)
        ]

    def on_upload(self) -> None:
        """Any YAML save may create or replace a playbook; mark cache stale."""
        self.mark_stale()

    def on_delete(self) -> None:
        """Any delete may remove playbooks; mark cache stale."""
        self.mark_stale()

    def _index_entry(self, playbook: Mapping[str, Any]) -> JsonDict:
        return playbook_summary(playbook)

    def _write_all(self, playbooks: Sequence[Mapping[str, Any]], *, complete: bool) -> None:
        if self.root.exists():
            self.invalidate()
        self.playbooks_dir.mkdir(parents=True, exist_ok=True)
        index: JsonDict = {"by_id": {}, "by_name": {}}
        for playbook in playbooks:
            pid = str(playbook.get("id") or "")
            if not pid:
                continue
            self._write_playbook_file(playbook)
            summary = self._index_entry(playbook)
            name = str(summary.get("name") or "")
            index["by_id"][pid] = summary
            index["by_name"].setdefault(name, [])
            if pid not in index["by_name"][name]:
                index["by_name"][name].append(pid)
        self.index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
        meta = CacheMeta(
            url=self.credentials.url,
            platform=self.credentials.platform.value,
            fetched_at=time.time(),
            ttl_seconds=self.ttl_seconds,
            playbook_count=len(index["by_id"]),
            complete=complete,
        )
        self.meta_path.write_text(json.dumps(meta.to_dict(), indent=2), encoding="utf-8")
        self.write_manifest()

    def _upsert(self, playbook: Mapping[str, Any]) -> None:
        self.playbooks_dir.mkdir(parents=True, exist_ok=True)
        self._write_playbook_file(playbook)
        index = self._load_index()
        summary = self._index_entry(playbook)
        pid = str(summary.get("id") or "")
        name = str(summary.get("name") or "")
        if not pid:
            return
        old = (index.get("by_id") or {}).get(pid) or {}
        old_name = old.get("name")
        index.setdefault("by_id", {})[pid] = summary
        index.setdefault("by_name", {})
        if old_name and old_name != name:
            names = [x for x in (index["by_name"].get(old_name) or []) if x != pid]
            if names:
                index["by_name"][old_name] = names
            else:
                index["by_name"].pop(old_name, None)
        index["by_name"].setdefault(name, [])
        if pid not in index["by_name"][name]:
            index["by_name"][name].append(pid)
        self.index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
        existing = self.meta()
        complete = bool(existing and existing.complete)
        fetched_at = existing.fetched_at if existing else time.time()
        meta = CacheMeta(
            url=self.credentials.url,
            platform=self.credentials.platform.value,
            fetched_at=fetched_at,
            ttl_seconds=self.ttl_seconds,
            playbook_count=len(index["by_id"]),
            complete=complete,
        )
        self.meta_path.write_text(json.dumps(meta.to_dict(), indent=2), encoding="utf-8")
        self.write_manifest()

    def _write_playbook_file(self, playbook: Mapping[str, Any]) -> None:
        pid = str(playbook.get("id") or "")
        path = self.playbooks_dir / f"{_safe_filename(pid)}.json"
        path.write_text(json.dumps(playbook, indent=2, default=str), encoding="utf-8")

    def _read_playbook(self, playbook_id: str) -> Optional[JsonDict]:
        path = self.playbooks_dir / f"{_safe_filename(playbook_id)}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return normalize_playbook(data) if isinstance(data, dict) else None

    def _load_all(self) -> List[JsonDict]:
        playbooks: List[JsonDict] = []
        if not self.playbooks_dir.exists():
            return playbooks
        for path in sorted(self.playbooks_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                playbooks.append(normalize_playbook(data))
        return playbooks

    def _load_index(self) -> JsonDict:
        if not self.index_path.exists():
            return {"by_id": {}, "by_name": {}}
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"by_id": {}, "by_name": {}}
        if not isinstance(data, dict):
            return {"by_id": {}, "by_name": {}}
        data.setdefault("by_id", {})
        data.setdefault("by_name", {})
        return data


def _safe_filename(playbook_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in playbook_id)
