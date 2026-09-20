"""Filesystem paths for data, collections, and cache."""

from __future__ import annotations

import os
from pathlib import Path


def package_root() -> Path:
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    raw = os.environ.get("CORTEX_PS_DATA_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return package_root() / "data"


def collections_dir() -> Path:
    return data_dir() / "collections"


def credentials_collection_path() -> Path:
    return collections_dir() / "credentials.json"


def cache_root() -> Path:
    return data_dir() / "cache"


def profile_cache_dir(cache_key: str) -> Path:
    return cache_root() / cache_key
