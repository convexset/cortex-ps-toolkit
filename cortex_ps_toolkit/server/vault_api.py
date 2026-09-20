"""HTTP handlers for the local integration credential vault."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..vault.store import (
    VaultError,
    VaultLocked,
    VaultPassphraseError,
    add_entry,
    add_passphrase_wrap,
    init_vault,
    list_entries,
    list_wraps,
    lock_vault,
    revoke_passphrase_wrap,
    status,
    unlock_vault,
)
from .common import read_json, run_sync


def _vault_error(exc: Exception) -> JSONResponse:
    if isinstance(exc, VaultPassphraseError):
        return JSONResponse({"error": str(exc)}, status_code=401)
    if isinstance(exc, VaultLocked):
        return JSONResponse({"error": str(exc)}, status_code=423)
    return JSONResponse({"error": str(exc)}, status_code=400)


async def api_vault_status(_request: Request) -> JSONResponse:
    return JSONResponse(await run_sync(status))


async def api_vault_init(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        passphrase = str(body.get("passphrase") or "")
        alias = str(body.get("alias") or "primary")
        result = await run_sync(init_vault, passphrase, alias=alias)
        return JSONResponse(result, status_code=201)
    except VaultError as exc:
        return _vault_error(exc)


async def api_vault_unlock(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        passphrase = str(body.get("passphrase") or "")
        result = await run_sync(unlock_vault, passphrase)
        return JSONResponse(result)
    except VaultPassphraseError as exc:
        return _vault_error(exc)


async def api_vault_lock(_request: Request) -> JSONResponse:
    return JSONResponse(await run_sync(lock_vault))


async def api_vault_wraps(_request: Request) -> JSONResponse:
    try:
        return JSONResponse({"wraps": await run_sync(list_wraps)})
    except VaultError as exc:
        return _vault_error(exc)


async def api_vault_wrap_add(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        result = await run_sync(
            add_passphrase_wrap,
            current_passphrase=str(body.get("current_passphrase") or ""),
            new_passphrase=str(body.get("new_passphrase") or ""),
            alias=str(body.get("alias") or ""),
        )
        return JSONResponse(result)
    except VaultError as exc:
        return _vault_error(exc)


async def api_vault_wrap_revoke(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        result = await run_sync(
            revoke_passphrase_wrap,
            passphrase=str(body.get("passphrase") or ""),
            alias=str(body.get("alias") or ""),
        )
        return JSONResponse(result)
    except VaultError as exc:
        return _vault_error(exc)


async def api_vault_entries(_request: Request) -> JSONResponse:
    try:
        entries = await run_sync(list_entries, masked=True)
        return JSONResponse({"entries": entries, "count": len(entries)})
    except VaultError as exc:
        return _vault_error(exc)


async def api_vault_entries_create(request: Request) -> JSONResponse:
    try:
        body = await read_json(request)
        entry = await run_sync(
            add_entry,
            name=str(body.get("name") or ""),
            user=str(body.get("user") or ""),
            password=str(body.get("password") or ""),
            workgroup=str(body.get("workgroup") or ""),
            certificate=str(body.get("certificate") or ""),
            certificate_pass=str(body.get("certificate_pass") or ""),
            notes=str(body.get("notes") or ""),
            tags=body.get("tags") if isinstance(body.get("tags"), list) else [],
        )
        return JSONResponse(entry, status_code=201)
    except VaultError as exc:
        return _vault_error(exc)
