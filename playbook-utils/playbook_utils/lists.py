"""Copy XSOAR/XSIAM lists between tenants via /xsoar/public/v1/lists."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence
from urllib.parse import quote

from .client import PlaybookApiError, PlaybookClient, UnsupportedOnTenant, _json_or_raw
from .credentials import Platform
from .keys import JsonDict


@dataclass(frozen=True)
class ListRecord:
    id: str
    name: str
    list_type: str
    version: int
    data: str
    meta: JsonDict

    @classmethod
    def from_meta(cls, meta: JsonDict, *, data: str) -> "ListRecord":
        list_id = str(meta.get("id") or meta.get("name") or "")
        name = str(meta.get("name") or list_id)
        list_type = str(meta.get("type") or "plaintext")
        version = int(meta.get("version") or 0)
        return cls(id=list_id, name=name, list_type=list_type, version=version, data=data, meta=dict(meta))


@dataclass(frozen=True)
class ListCopyOutcome:
    source_name: str
    target_name: str
    ok: bool
    created: bool
    source_id: str
    target_id: str
    target_version: Optional[int] = None
    error: Optional[str] = None
    response: Optional[JsonDict] = None

    def to_dict(self) -> JsonDict:
        return {
            "source_name": self.source_name,
            "target_name": self.target_name,
            "ok": self.ok,
            "created": self.created,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "target_version": self.target_version,
            "error": self.error,
            "response": self.response,
        }


def _lists_base(client: PlaybookClient) -> str:
    if client.credentials.platform not in {Platform.XSOAR8, Platform.XSIAM}:
        raise UnsupportedOnTenant(
            f"Lists API is supported on XSOAR 8 and XSIAM only (tenant={client.credentials.platform.value})"
        )
    return f"{client.credentials.host}/xsoar/public/v1/lists"


def list_all(client: PlaybookClient) -> List[ListRecord]:
    """Return all lists on the tenant."""
    response = client.session.get(_lists_base(client), timeout=client.timeout)
    client._raise_for_status(response, "lists get all")
    payload = response.json()
    if not isinstance(payload, list):
        raise PlaybookApiError(f"lists get all returned non-array: {type(payload)}")
    records: List[ListRecord] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        data = str(item.get("data") or "")
        if not data:
            data = download_list_data(client, str(item.get("id") or item.get("name") or ""))
        records.append(ListRecord.from_meta(item, data=data))
    return records


def _find_list_meta(client: PlaybookClient, name_or_id: str) -> JsonDict:
    response = client.session.get(_lists_base(client), timeout=client.timeout)
    client._raise_for_status(response, "lists get all")
    payload = response.json()
    if not isinstance(payload, list):
        raise PlaybookApiError(f"lists get all returned non-array: {type(payload)}")
    needle = str(name_or_id)
    matches = [
        item
        for item in payload
        if isinstance(item, dict)
        and (str(item.get("id") or "") == needle or str(item.get("name") or "") == needle)
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise PlaybookApiError(f"List {name_or_id!r} is ambiguous ({len(matches)} matches)")
    raise PlaybookApiError(f"List {name_or_id!r} not found", status_code=404)


def download_list_data(client: PlaybookClient, list_id: str) -> str:
    encoded = quote(str(list_id), safe="")
    response = client.session.get(
        f"{_lists_base(client)}/download/{encoded}",
        timeout=client.timeout,
    )
    client._raise_for_status(response, f"lists download {list_id}")
    return response.text


def get_list(client: PlaybookClient, name_or_id: str) -> ListRecord:
    meta = _find_list_meta(client, name_or_id)
    list_id = str(meta.get("id") or meta.get("name") or name_or_id)
    data = str(meta.get("data") or "")
    if not data:
        data = download_list_data(client, list_id)
    return ListRecord.from_meta(meta, data=data)


def save_list(
    client: PlaybookClient,
    record: ListRecord,
    *,
    target_name: Optional[str] = None,
    overwrite: bool = True,
    commit_message: str = "Copied via playbook-utils",
) -> JsonDict:
    """Create or update a list on the tenant."""
    name = str(target_name or record.name)
    payload: JsonDict = {
        "name": name,
        "type": record.list_type,
        "data": record.data,
        "allRead": bool(record.meta.get("allRead", True)),
        "allReadWrite": bool(record.meta.get("allReadWrite", True)),
        "propagationLabels": record.meta.get("propagationLabels") or ["all"],
        "shouldCommit": True,
        "commitMessage": commit_message,
    }
    if overwrite:
        try:
            existing = _find_list_meta(client, name)
        except PlaybookApiError as exc:
            if exc.status_code != 404:
                raise
        else:
            payload["id"] = existing.get("id")
            payload["version"] = existing.get("version")
    response = client.session.post(
        f"{_lists_base(client)}/save",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=client.timeout,
    )
    client._raise_for_status(response, f"lists save {name}")
    return _json_or_raw(response)


def delete_list(client: PlaybookClient, name_or_id: str) -> JsonDict:
    meta = _find_list_meta(client, name_or_id)
    list_id = str(meta.get("id") or meta.get("name") or name_or_id)
    response = client.session.post(
        f"{_lists_base(client)}/delete",
        json={"id": list_id},
        headers={"Content-Type": "application/json"},
        timeout=client.timeout,
    )
    client._raise_for_status(response, f"lists delete {list_id}")
    return _json_or_raw(response)


def copy_list(
    source: PlaybookClient,
    target: PlaybookClient,
    name_or_id: str,
    *,
    target_name: Optional[str] = None,
    overwrite: bool = True,
    commit_message: str = "Copied via playbook-utils",
) -> ListCopyOutcome:
    """Copy one list from ``source`` tenant to ``target`` tenant."""
    try:
        record = get_list(source, name_or_id)
        created = True
        resolved_target_name = str(target_name or record.name)
        if overwrite:
            try:
                _find_list_meta(target, resolved_target_name)
                created = False
            except PlaybookApiError as exc:
                if exc.status_code != 404:
                    raise
        response = save_list(
            target,
            record,
            target_name=resolved_target_name,
            overwrite=overwrite,
            commit_message=commit_message,
        )
        target_id = str(response.get("id") or resolved_target_name)
        return ListCopyOutcome(
            source_name=record.name,
            target_name=resolved_target_name,
            ok=True,
            created=created,
            source_id=record.id,
            target_id=target_id,
            target_version=int(response.get("version") or 0) if response.get("version") is not None else None,
            response=response,
        )
    except PlaybookApiError as exc:
        return ListCopyOutcome(
            source_name=str(name_or_id),
            target_name=str(target_name or name_or_id),
            ok=False,
            created=False,
            source_id="",
            target_id="",
            error=str(exc),
        )


def copy_lists(
    source: PlaybookClient,
    target: PlaybookClient,
    names: Sequence[str],
    *,
    target_name_prefix: str = "",
    overwrite: bool = True,
    commit_message: str = "Copied via playbook-utils",
) -> List[ListCopyOutcome]:
    outcomes: List[ListCopyOutcome] = []
    for name in names:
        target_name = f"{target_name_prefix}{name}" if target_name_prefix else None
        outcomes.append(
            copy_list(
                source,
                target,
                name,
                target_name=target_name,
                overwrite=overwrite,
                commit_message=commit_message,
            )
        )
    return outcomes


def format_list_copy_report(outcomes: Sequence[ListCopyOutcome]) -> str:
    ok_count = sum(1 for item in outcomes if item.ok)
    lines = [f"Copied: {ok_count}/{len(outcomes)}"]
    for item in outcomes:
        status = "ok" if item.ok else "FAIL"
        action = "created" if item.created else "updated"
        suffix = f" ({action})" if item.ok else ""
        lines.append(
            f"  [{status}] {item.source_name} -> {item.target_name} [{item.target_id}]{suffix}"
        )
        if item.error and not item.ok:
            lines.append(f"         {item.error}")
    return "\n".join(lines)
