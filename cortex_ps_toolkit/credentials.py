"""Credential profile management (server-side JSON collection)."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from urllib.parse import urlparse

from .collections import bump_collection, load_collection, save_collection
from .paths import credentials_collection_path, profile_cache_dir
from .platforms import Platform, detect_platform, parse_platform

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_expiry(value: str) -> str:
    """Parse human or ISO expiry into UTC end-of-period ISO8601.

    Examples:
        ``2026-11-30`` — end of that calendar day (UTC)
        ``end Nov 2026`` — last moment of November 2026 (UTC)
    """
    text = value.strip()
    if not text:
        raise ValueError("Expiry value cannot be empty")

    lowered = text.lower()
    if lowered.startswith("end "):
        parts = lowered.split()
        if len(parts) == 3 and parts[1] in _MONTHS and parts[2].isdigit():
            year = int(parts[2])
            month = _MONTHS[parts[1]]
            last_day = monthrange(year, month)[1]
            dt = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            f"Unrecognised expiry {value!r}; use ISO date (2026-11-30) or 'end Nov 2026'"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    if len(text) <= 10:
        parsed = parsed.replace(hour=23, minute=59, second=59)
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def is_expired(profile: "CredentialProfile", *, now: Optional[datetime] = None) -> bool:
    if not profile.expires_at:
        return False
    moment = now or _utc_now()
    expires = datetime.fromisoformat(profile.expires_at.replace("Z", "+00:00"))
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return moment > expires


def slugify_label(label: str) -> str:
    text = label.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "profile"


def sanitize_host_dir(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.netloc or parsed.path or url).lower().rstrip("/")
    return "".join(ch if ch.isalnum() or ch in ".-" else "_" for ch in host) or "tenant"


@dataclass(frozen=True)
class CredentialProfile:
    id: str
    label: str
    slug: str
    url: str
    api_id: str
    key: str
    tenant_type: Platform
    verify_ssl: bool = True
    notes: str = ""
    expires_at: str = ""
    created_at: str = ""
    updated_at: str = ""
    cache_ttl_seconds: Optional[int] = None
    max_inflight_per_host: Optional[int] = None
    max_inflight_global: Optional[int] = None

    @property
    def host(self) -> str:
        parsed = urlparse(self.url)
        if parsed.scheme:
            return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        return self.url.rstrip("/")

    @property
    def cache_key(self) -> str:
        api_segment = self.api_id or "_"
        return f"{sanitize_host_dir(self.url)}/{self.tenant_type.value}/{api_segment}"

    def to_public_dict(self) -> dict[str, Any]:
        """Safe for list views — masks secret key."""
        masked = self.key[:4] + "…" if len(self.key) > 4 else "****"
        return {
            "id": self.id,
            "label": self.label,
            "slug": self.slug,
            "url": self.url,
            "api_id": self.api_id,
            "key_masked": masked,
            "tenant_type": self.tenant_type.value,
            "verify_ssl": self.verify_ssl,
            "notes": self.notes,
            "expires_at": self.expires_at or None,
            "expired": is_expired(self),
            "cache_key": self.cache_key,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "max_inflight_per_host": self.max_inflight_per_host,
            "max_inflight_global": self.max_inflight_global,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_storage_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "slug": self.slug,
            "url": self.url,
            "api_id": self.api_id,
            "key": self.key,
            "tenant_type": self.tenant_type.value,
            "verify_ssl": self.verify_ssl,
            "notes": self.notes,
            "expires_at": self.expires_at,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "max_inflight_per_host": self.max_inflight_per_host,
            "max_inflight_global": self.max_inflight_global,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_storage_dict(cls, payload: Mapping[str, Any]) -> "CredentialProfile":
        tenant_raw = str(payload.get("tenant_type") or payload.get("platform") or "")
        url = str(payload.get("url") or "").strip()
        tenant_type = parse_platform(tenant_raw) if tenant_raw else detect_platform(url)
        profile_id = str(payload.get("id") or uuid.uuid4())
        raw_api_id = payload.get("api_id", payload.get("key_id"))
        api_id = str(raw_api_id) if raw_api_id is not None and str(raw_api_id) != "" else ""
        label = str(payload.get("label") or payload.get("slug") or profile_id)
        slug = str(payload.get("slug") or slugify_label(label))
        key = str(payload.get("key") or payload.get("api_key") or "")
        if not url or not key:
            raise ValueError("Credential profile requires url and key")
        return cls(
            id=str(profile_id),
            label=label,
            slug=slug,
            url=url,
            api_id=api_id,
            key=key,
            tenant_type=tenant_type,
            verify_ssl=bool(payload.get("verify_ssl", True)),
            notes=str(payload.get("notes") or ""),
            expires_at=str(payload.get("expires_at") or ""),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            cache_ttl_seconds=_optional_positive_int(payload.get("cache_ttl_seconds")),
            max_inflight_per_host=_optional_positive_int(payload.get("max_inflight_per_host")),
            max_inflight_global=_optional_positive_int(payload.get("max_inflight_global")),
        )


def _optional_positive_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def load_credentials_collection(path: Optional[Path] = None) -> dict[str, Any]:
    return load_collection(path or credentials_collection_path(), default={"version": 1, "profiles": []})


def save_credentials_collection(payload: Mapping[str, Any], path: Optional[Path] = None) -> None:
    save_collection(path or credentials_collection_path(), payload)


def list_profiles(path: Optional[Path] = None, *, include_expired: bool = False) -> list[CredentialProfile]:
    payload = load_credentials_collection(path)
    profiles = payload.get("profiles") or []
    result = [CredentialProfile.from_storage_dict(item) for item in profiles if isinstance(item, Mapping)]
    if include_expired:
        return result
    return [profile for profile in result if not is_expired(profile)]


def remove_profile_cache(profile: CredentialProfile) -> bool:
    cache_dir = profile_cache_dir(profile.cache_key)
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
        return True
    return False


def remove_profile(slug_or_id: str, path: Optional[Path] = None) -> CredentialProfile:
    collection_path = path or credentials_collection_path()
    payload = load_credentials_collection(collection_path)
    profiles: list[dict[str, Any]] = list(payload.get("profiles") or [])
    removed: Optional[CredentialProfile] = None
    kept: list[dict[str, Any]] = []
    for item in profiles:
        profile = CredentialProfile.from_storage_dict(item)
        if profile.slug == slug_or_id or profile.id == slug_or_id or profile.label == slug_or_id:
            removed = profile
            continue
        kept.append(item)
    if removed is None:
        raise KeyError(f"Credential profile not found: {slug_or_id!r}")
    payload["profiles"] = kept
    bump_collection(payload)
    save_credentials_collection(payload, collection_path)
    remove_profile_cache(removed)
    return removed


def set_profile_verify_ssl(
    slug_or_id: str,
    verify_ssl: bool,
    path: Optional[Path] = None,
) -> CredentialProfile:
    profile = get_profile(slug_or_id, path)
    updated = CredentialProfile(
        id=profile.id,
        label=profile.label,
        slug=profile.slug,
        url=profile.url,
        api_id=profile.api_id,
        key=profile.key,
        tenant_type=profile.tenant_type,
        verify_ssl=verify_ssl,
        notes=profile.notes,
        expires_at=profile.expires_at,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        cache_ttl_seconds=profile.cache_ttl_seconds,
        max_inflight_per_host=profile.max_inflight_per_host,
        max_inflight_global=profile.max_inflight_global,
    )
    return upsert_profile(updated, path)


def set_profile_expiry(
    slug_or_id: str,
    expires_at: Optional[str],
    path: Optional[Path] = None,
) -> CredentialProfile:
    profile = get_profile(slug_or_id, path)
    normalized = parse_expiry(expires_at) if expires_at else ""
    updated = CredentialProfile(
        id=profile.id,
        label=profile.label,
        slug=profile.slug,
        url=profile.url,
        api_id=profile.api_id,
        key=profile.key,
        tenant_type=profile.tenant_type,
        verify_ssl=profile.verify_ssl,
        notes=profile.notes,
        expires_at=normalized,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        cache_ttl_seconds=profile.cache_ttl_seconds,
        max_inflight_per_host=profile.max_inflight_per_host,
        max_inflight_global=profile.max_inflight_global,
    )
    return upsert_profile(updated, path)


def purge_expired_profiles(
    path: Optional[Path] = None,
    *,
    dry_run: bool = False,
) -> list[CredentialProfile]:
    collection_path = path or credentials_collection_path()
    payload = load_credentials_collection(collection_path)
    profiles_raw: list[dict[str, Any]] = list(payload.get("profiles") or [])
    expired: list[CredentialProfile] = []
    active: list[dict[str, Any]] = []
    for item in profiles_raw:
        profile = CredentialProfile.from_storage_dict(item)
        if is_expired(profile):
            expired.append(profile)
            if not dry_run:
                remove_profile_cache(profile)
        else:
            active.append(item)
    if expired and not dry_run:
        payload["profiles"] = active
        bump_collection(payload)
        save_credentials_collection(payload, collection_path)
    return expired


def get_profile(slug_or_id: str, path: Optional[Path] = None) -> CredentialProfile:
    for profile in list_profiles(path, include_expired=True):
        if profile.slug == slug_or_id or profile.id == slug_or_id or profile.label == slug_or_id:
            return profile
    raise KeyError(f"Credential profile not found: {slug_or_id!r}")


def upsert_profile(profile: CredentialProfile, path: Optional[Path] = None) -> CredentialProfile:
    collection_path = path or credentials_collection_path()
    payload = load_credentials_collection(collection_path)
    bump_collection(payload)
    profiles: list[dict[str, Any]] = list(payload.get("profiles") or [])
    now = _utc_now_iso()
    stored = profile.to_storage_dict()
    replaced = False
    for index, existing in enumerate(profiles):
        if existing.get("slug") == profile.slug or existing.get("id") == profile.id:
            stored["id"] = str(existing.get("id") or stored.get("id") or uuid.uuid4())
            stored.setdefault("created_at", existing.get("created_at") or now)
            stored["updated_at"] = now
            profiles[index] = stored
            replaced = True
            break
    if not replaced:
        stored.setdefault("id", str(uuid.uuid4()))
        stored.setdefault("created_at", now)
        stored["updated_at"] = now
        profiles.append(stored)
    payload["profiles"] = profiles
    save_credentials_collection(payload, collection_path)
    return CredentialProfile.from_storage_dict(stored)


def profile_from_source_file(
    source_path: Path,
    *,
    label: str,
    slug: str,
    tenant_type: Platform,
    notes: str = "",
    expires_at: str = "",
    verify_ssl: Optional[bool] = None,
) -> CredentialProfile:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Credential source must be a JSON object: {source_path}")
    url = str(payload.get("url") or "").strip()
    key = str(payload.get("key") or payload.get("api_key") or "").strip()
    raw_id = payload.get("id", payload.get("api_id"))
    api_id = str(raw_id) if raw_id is not None and str(raw_id) != "" else ""
    if not url or not key:
        raise ValueError(f"Credential source missing url/key: {source_path}")
    ssl = bool(payload.get("verify_ssl", True)) if verify_ssl is None else verify_ssl
    if verify_ssl is None and "verify" in payload:
        ssl = bool(payload.get("verify"))
    now = _utc_now_iso()
    return CredentialProfile(
        id=str(uuid.uuid4()),
        label=label,
        slug=slug,
        url=url,
        api_id=api_id,
        key=key,
        tenant_type=tenant_type,
        verify_ssl=ssl,
        notes=notes,
        expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )


def create_profile_from_input(data: Mapping[str, Any]) -> CredentialProfile:
    label = str(data.get("label") or "").strip()
    if not label:
        raise ValueError("label is required")
    slug = str(data.get("slug") or slugify_label(label))
    url = str(data.get("url") or "").strip()
    key = str(data.get("key") or data.get("api_key") or "").strip()
    if not url or not key:
        raise ValueError("url and key are required")
    tenant_raw = data.get("tenant_type") or data.get("platform")
    tenant_type = parse_platform(str(tenant_raw)) if tenant_raw else detect_platform(url)
    raw_id = data.get("api_id", data.get("id"))
    api_id = str(raw_id) if raw_id is not None and str(raw_id) != "" else ""
    expires_raw = data.get("expires_at") or data.get("expires")
    expires_at = parse_expiry(str(expires_raw)) if expires_raw else ""
    now = _utc_now_iso()
    profile = CredentialProfile(
        id=str(uuid.uuid4()),
        label=label,
        slug=slug,
        url=url,
        api_id=api_id,
        key=key,
        tenant_type=tenant_type,
        verify_ssl=bool(data.get("verify_ssl", True)),
        notes=str(data.get("notes") or ""),
        expires_at=expires_at,
        created_at=now,
        updated_at=now,
        cache_ttl_seconds=_optional_positive_int(data.get("cache_ttl_seconds")),
        max_inflight_per_host=_optional_positive_int(data.get("max_inflight_per_host")),
        max_inflight_global=_optional_positive_int(data.get("max_inflight_global")),
    )
    return upsert_profile(profile)


def update_profile_from_input(slug_or_id: str, data: Mapping[str, Any]) -> CredentialProfile:
    existing = get_profile(slug_or_id)
    label = str(data.get("label") or existing.label).strip()
    slug = str(data.get("slug") or existing.slug)
    url = str(data.get("url") or existing.url).strip()
    key_raw = data.get("key") or data.get("api_key")
    key = str(key_raw).strip() if key_raw not in (None, "") else existing.key
    tenant_raw = data.get("tenant_type") or data.get("platform")
    tenant_type = parse_platform(str(tenant_raw)) if tenant_raw else existing.tenant_type
    raw_id = data.get("api_id", data.get("id"))
    api_id = str(raw_id) if raw_id is not None and str(raw_id) != "" else existing.api_id
    expires_at = existing.expires_at
    if "expires_at" in data or "expires" in data:
        expires_raw = data.get("expires_at") if "expires_at" in data else data.get("expires")
        expires_at = parse_expiry(str(expires_raw)) if expires_raw else ""
    verify_ssl = existing.verify_ssl if "verify_ssl" not in data else bool(data.get("verify_ssl"))
    notes = str(data.get("notes") if "notes" in data else existing.notes)
    cache_ttl = existing.cache_ttl_seconds
    if "cache_ttl_seconds" in data:
        cache_ttl = _optional_positive_int(data.get("cache_ttl_seconds"))
    max_host = existing.max_inflight_per_host
    if "max_inflight_per_host" in data:
        max_host = _optional_positive_int(data.get("max_inflight_per_host"))
    max_global = existing.max_inflight_global
    if "max_inflight_global" in data:
        max_global = _optional_positive_int(data.get("max_inflight_global"))
    updated = CredentialProfile(
        id=existing.id,
        label=label,
        slug=slug,
        url=url,
        api_id=api_id,
        key=key,
        tenant_type=tenant_type,
        verify_ssl=verify_ssl,
        notes=notes,
        expires_at=expires_at,
        created_at=existing.created_at,
        updated_at=existing.updated_at,
        cache_ttl_seconds=cache_ttl,
        max_inflight_per_host=max_host,
        max_inflight_global=max_global,
    )
    return upsert_profile(updated)


def import_lab_profiles(
    sources: Sequence[Mapping[str, Any]],
    *,
    base_dir: Path,
    destination: Optional[Path] = None,
) -> list[CredentialProfile]:
    imported: list[CredentialProfile] = []
    for source in sources:
        slug = str(source.get("slug") or "")
        label = str(source.get("label") or slug)
        tenant_type = parse_platform(str(source.get("tenant_type") or ""))
        source_file = str(source.get("source_file") or "")
        notes = str(source.get("notes") or "")
        expires_raw = source.get("expires") or source.get("expires_at")
        expires_at = parse_expiry(str(expires_raw)) if expires_raw else ""
        verify_ssl = source.get("verify_ssl")
        verify_override = bool(verify_ssl) if verify_ssl is not None else None
        if not slug or not source_file:
            raise ValueError(f"Lab source entry missing slug or source_file: {source!r}")
        source_path = (base_dir / source_file).resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Credential source not found: {source_path}")
        profile = profile_from_source_file(
            source_path,
            label=label,
            slug=slug,
            tenant_type=tenant_type,
            notes=notes,
            expires_at=expires_at,
            verify_ssl=verify_override,
        )
        imported.append(upsert_profile(profile, destination))
    return imported
