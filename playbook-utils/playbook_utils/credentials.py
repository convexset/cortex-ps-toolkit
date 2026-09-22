"""Load tenant credentials from a JSON file."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import urlparse


class Platform(str, Enum):
    XSOAR6 = "xsoar6"
    XSOAR8 = "xsoar8"
    XSIAM = "xsiam"

    def supports_bulk_search(self) -> bool:
        return self in {Platform.XSOAR6, Platform.XSOAR8, Platform.XSIAM}

    def requires_auth_id(self) -> bool:
        return self in {Platform.XSOAR8, Platform.XSIAM}


def parse_tenant_type(value: str) -> Platform:
    text = value.strip().lower()
    aliases = {
        "xsiam": Platform.XSIAM,
        "xsoar8": Platform.XSOAR8,
        "xsoar-8": Platform.XSOAR8,
        "8": Platform.XSOAR8,
        "xsoar6": Platform.XSOAR6,
        "xsoar-6": Platform.XSOAR6,
        "6": Platform.XSOAR6,
    }
    if text not in aliases:
        raise ValueError(f"Unknown tenant type {value!r}; use xsoar6, xsoar8, or xsiam")
    return aliases[text]


def detect_platform(url: str, explicit: Optional[str] = None) -> Platform:
    if explicit:
        return parse_tenant_type(explicit)
    host = (urlparse(url).netloc or url).lower()
    path = (urlparse(url).path or "").lower()
    if "xsiam" in host or ".xdr." in host:
        return Platform.XSIAM
    if "crtx." in host or "/xsoar/public/v1" in path:
        return Platform.XSOAR8
    return Platform.XSOAR6


def sanitize_host_dir(url: str) -> str:
    """Filesystem-safe directory name for a tenant URL (host only)."""
    parsed = urlparse(url)
    host = (parsed.netloc or parsed.path or url).lower().rstrip("/")
    return "".join(ch if ch.isalnum() or ch in ".-" else "_" for ch in host) or "tenant"


@dataclass(frozen=True)
class Credentials:
    url: str
    key: str
    api_id: Optional[str]
    platform: Platform
    verify_ssl: bool = True

    @property
    def host(self) -> str:
        parsed = urlparse(self.url)
        if parsed.scheme:
            return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        return self.url.rstrip("/")

    @property
    def cache_key(self) -> str:
        """Cache is segregated by host URL, then tenant type."""
        return f"{sanitize_host_dir(self.url)}/{self.platform.value}"


def load_credentials(path: str, *, platform: Optional[str] = None, verify_ssl: Optional[bool] = None) -> Credentials:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Credentials file must be a JSON object: {path}")
    url = str(payload.get("url") or "").strip()
    key = str(payload.get("key") or payload.get("api_key") or "").strip()
    if not url or not key:
        raise ValueError("Credentials file must contain 'url' and 'key'")
    raw_id = payload.get("id", payload.get("api_id"))
    api_id = str(raw_id) if raw_id is not None and str(raw_id) != "" else None
    file_type = payload.get("tenant_type") or payload.get("platform")
    resolved = detect_platform(url, platform or (str(file_type) if file_type else None))
    ssl = True if verify_ssl is None else verify_ssl
    if verify_ssl is None and "verify" in payload:
        ssl = bool(payload.get("verify"))
    return Credentials(url=url, key=key, api_id=api_id, platform=resolved, verify_ssl=ssl)
