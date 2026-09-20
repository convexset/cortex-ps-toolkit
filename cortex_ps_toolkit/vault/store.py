"""Encrypted integration credential vault (VMK + alias wrap slots)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..paths import data_dir
from . import crypto, session

VAULT_VERSION = 2


class VaultError(Exception):
    pass


class VaultLocked(VaultError):
    pass


class VaultPassphraseError(VaultError):
    pass


def vault_dir() -> Path:
    return data_dir() / "vault"


def vault_path() -> Path:
    return vault_dir() / "integration-credentials.vault.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def vault_exists() -> bool:
    return vault_path().is_file()


def _load_file() -> dict[str, Any]:
    path = vault_path()
    if not path.is_file():
        raise VaultError("Vault not initialized")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise VaultError("Vault file is corrupt")
    return data


def _save_file(data: dict[str, Any]) -> None:
    vault_dir().mkdir(parents=True, exist_ok=True)
    path = vault_path()
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _unwrap_vmk(data: dict[str, Any], passphrase: str) -> bytes:
    wraps = data.get("wraps") or []
    last_error: Optional[Exception] = None
    for wrap in wraps:
        if not isinstance(wrap, dict):
            continue
        try:
            salt = crypto.b64decode(str(wrap.get("salt") or ""))
            nonce = crypto.b64decode(str(wrap.get("nonce") or ""))
            ciphertext = crypto.b64decode(str(wrap.get("ciphertext") or ""))
            key = crypto.derive_key(passphrase, salt)
            vmk = crypto.decrypt(key, nonce, ciphertext)
            if len(vmk) != 32:
                continue
            return vmk
        except Exception as exc:
            last_error = exc
            continue
    raise VaultPassphraseError("Invalid passphrase") from last_error


def _encrypt_entries(vmk: bytes, entries: list[dict[str, Any]]) -> tuple[str, str]:
    nonce, ciphertext = crypto.encrypt(vmk, json.dumps(entries).encode("utf-8"))
    return crypto.b64encode(nonce), crypto.b64encode(ciphertext)


def _decrypt_entries(vmk: bytes, data: dict[str, Any]) -> list[dict[str, Any]]:
    nonce = crypto.b64decode(str(data.get("entries_nonce") or ""))
    ciphertext = crypto.b64decode(str(data.get("entries_ciphertext") or ""))
    plaintext = crypto.decrypt(vmk, nonce, ciphertext)
    entries = json.loads(plaintext.decode("utf-8"))
    if not isinstance(entries, list):
        raise VaultError("Vault entries payload is corrupt")
    return [item for item in entries if isinstance(item, dict)]


def init_vault(passphrase: str, *, alias: str = "primary") -> dict[str, Any]:
    if vault_exists():
        raise VaultError("Vault already initialized")
    if not passphrase.strip():
        raise VaultError("Passphrase cannot be empty")
    if not alias.strip():
        raise VaultError("Passphrase alias cannot be empty")

    vmk = os.urandom(32)
    salt = os.urandom(16)
    key = crypto.derive_key(passphrase, salt)
    wrap_nonce, wrap_ciphertext = crypto.encrypt(key, vmk)
    entries_nonce, entries_ciphertext = _encrypt_entries(vmk, [])

    data = {
        "version": VAULT_VERSION,
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
        "wraps": [
            {
                "slot_id": str(uuid.uuid4()),
                "alias": alias.strip(),
                "created_at": _utc_now_iso(),
                "salt": crypto.b64encode(salt),
                "nonce": crypto.b64encode(wrap_nonce),
                "ciphertext": crypto.b64encode(wrap_ciphertext),
            }
        ],
        "entries_nonce": entries_nonce,
        "entries_ciphertext": entries_ciphertext,
    }
    _save_file(data)
    session.unlock_session(vmk)
    return public_status(data)


def unlock_vault(passphrase: str) -> dict[str, Any]:
    data = _load_file()
    vmk = _unwrap_vmk(data, passphrase)
    session.unlock_session(vmk)
    return status()


def lock_vault() -> dict[str, Any]:
    session.lock_session()
    return status()


def status() -> dict[str, Any]:
    result = session.session_status()
    result["initialized"] = vault_exists()
    if vault_exists():
        data = _load_file()
        result["wrap_count"] = len(data.get("wraps") or [])
        result["wrap_aliases"] = [
            str(item.get("alias") or item.get("slot_id"))
            for item in (data.get("wraps") or [])
            if isinstance(item, dict)
        ]
        result["updated_at"] = data.get("updated_at")
    return result


def public_status(data: dict[str, Any]) -> dict[str, Any]:
    wraps = [
        {
            "slot_id": item.get("slot_id"),
            "alias": item.get("alias"),
            "created_at": item.get("created_at"),
        }
        for item in (data.get("wraps") or [])
        if isinstance(item, dict)
    ]
    return {
        "initialized": True,
        "version": data.get("version"),
        "updated_at": data.get("updated_at"),
        "wraps": wraps,
        **session.session_status(),
    }


def list_wraps() -> list[dict[str, Any]]:
    data = _load_file()
    return [
        {
            "slot_id": item.get("slot_id"),
            "alias": item.get("alias"),
            "created_at": item.get("created_at"),
        }
        for item in (data.get("wraps") or [])
        if isinstance(item, dict)
    ]


def _require_vmk() -> bytes:
    vmk = session.get_vmk()
    if vmk is None:
        raise VaultLocked("Vault is locked")
    return vmk


def list_entries(*, masked: bool = True) -> list[dict[str, Any]]:
    data = _load_file()
    vmk = _require_vmk()
    entries = _decrypt_entries(vmk, data)
    rows: list[dict[str, Any]] = []
    for entry in entries:
        row = {
            "vault_id": entry.get("vault_id"),
            "name": entry.get("name"),
            "user": entry.get("user"),
            "workgroup": entry.get("workgroup"),
            "notes": entry.get("notes"),
            "tags": entry.get("tags") or [],
            "created_at": entry.get("created_at"),
            "updated_at": entry.get("updated_at"),
            "has_password": bool(entry.get("password")),
            "has_certificate": bool(entry.get("certificate")),
        }
        if not masked:
            row["password"] = entry.get("password")
            row["certificate"] = entry.get("certificate")
            row["certificate_pass"] = entry.get("certificate_pass")
        rows.append(row)
    return rows


def add_entry(
    *,
    name: str,
    user: str = "",
    password: str = "",
    workgroup: str = "",
    certificate: str = "",
    certificate_pass: str = "",
    notes: str = "",
    tags: Optional[list[str]] = None,
) -> dict[str, Any]:
    if not name.strip():
        raise VaultError("Entry name is required")
    data = _load_file()
    vmk = _require_vmk()
    entries = _decrypt_entries(vmk, data)
    now = _utc_now_iso()
    for entry in entries:
        if str(entry.get("name") or "").lower() == name.strip().lower():
            raise VaultError(f"Vault entry already exists: {name!r}")
    row = {
        "vault_id": str(uuid.uuid4()),
        "name": name.strip(),
        "user": user,
        "password": password,
        "workgroup": workgroup,
        "certificate": certificate,
        "certificate_pass": certificate_pass,
        "notes": notes,
        "tags": tags or [],
        "created_at": now,
        "updated_at": now,
    }
    entries.append(row)
    entries_nonce, entries_ciphertext = _encrypt_entries(vmk, entries)
    data["entries_nonce"] = entries_nonce
    data["entries_ciphertext"] = entries_ciphertext
    data["updated_at"] = now
    _save_file(data)
    return list_entries(masked=True)[-1]


def add_passphrase_wrap(*, current_passphrase: str, new_passphrase: str, alias: str) -> dict[str, Any]:
    if not new_passphrase.strip():
        raise VaultError("New passphrase cannot be empty")
    if not alias.strip():
        raise VaultError("Passphrase alias cannot be empty")
    data = _load_file()
    vmk = _unwrap_vmk(data, current_passphrase)
    session.unlock_session(vmk)
    for wrap in data.get("wraps") or []:
        if isinstance(wrap, dict) and str(wrap.get("alias") or "").lower() == alias.strip().lower():
            raise VaultError(f"Passphrase alias already exists: {alias!r}")

    salt = os.urandom(16)
    key = crypto.derive_key(new_passphrase, salt)
    wrap_nonce, wrap_ciphertext = crypto.encrypt(key, vmk)
    wraps = list(data.get("wraps") or [])
    wraps.append({
        "slot_id": str(uuid.uuid4()),
        "alias": alias.strip(),
        "created_at": _utc_now_iso(),
        "salt": crypto.b64encode(salt),
        "nonce": crypto.b64encode(wrap_nonce),
        "ciphertext": crypto.b64encode(wrap_ciphertext),
    })
    data["wraps"] = wraps
    data["updated_at"] = _utc_now_iso()
    _save_file(data)
    return public_status(data)


def revoke_passphrase_wrap(*, passphrase: str, alias: str) -> dict[str, Any]:
    if not alias.strip():
        raise VaultError("Passphrase alias is required")
    data = _load_file()
    vmk = _unwrap_vmk(data, passphrase)
    session.unlock_session(vmk)
    wraps = [item for item in (data.get("wraps") or []) if isinstance(item, dict)]
    remaining = [item for item in wraps if str(item.get("alias") or "") != alias.strip()]
    if len(remaining) == len(wraps):
        raise VaultError(f"No passphrase wrap found for alias: {alias!r}")
    if not remaining:
        raise VaultError("Cannot revoke the last passphrase wrap")
    data["wraps"] = remaining
    data["updated_at"] = _utc_now_iso()
    _save_file(data)
    return public_status(data)
