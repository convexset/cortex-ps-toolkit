"""Playbook HTTP client for XSOAR 6, XSOAR 8, and XSIAM."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any, List, Mapping, Optional
from urllib.parse import quote

import requests
import yaml

from .credentials import Credentials, Platform
from .keys import JsonDict, normalize_playbook
from .operation_log import timed_operation


class PlaybookApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class UnsupportedOnTenant(PlaybookApiError):
    """The tenant type does not expose this operation."""


def _zip_playbook_member(names: list[str]) -> str:
    """Prefer playbook YAML over pack ``metadata.json`` (XSIAM get ZIP layout)."""
    files = [name for name in names if not name.endswith("/")]
    yaml_members = [name for name in files if name.lower().endswith((".yml", ".yaml"))]
    if yaml_members:
        return yaml_members[0]
    json_members = [
        name
        for name in files
        if name.lower().endswith(".json") and name.rsplit("/", 1)[-1].lower() != "metadata.json"
    ]
    if json_members:
        return json_members[0]
    raise PlaybookApiError(f"ZIP contained no playbook YAML/JSON: {names!r}")


def decode_script_yaml_payload(data: bytes) -> str:
    """Extract automation YAML from XSIAM scripts/get ZIP payload."""
    if not data:
        raise PlaybookApiError("Empty script payload")
    raw = data
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            yaml_members = [
                name
                for name in archive.namelist()
                if name.lower().endswith((".yml", ".yaml")) and "/automation-" in name.replace("\\", "/")
            ]
            if not yaml_members:
                yaml_members = [name for name in archive.namelist() if name.lower().endswith((".yml", ".yaml"))]
            if not yaml_members:
                raise PlaybookApiError(f"ZIP contained no script YAML: {archive.namelist()!r}")
            raw = archive.read(yaml_members[0])
    return raw.decode("utf-8")


def decode_playbook_payload(data: bytes) -> JsonDict:
    """Parse a playbook from ZIP/YAML/JSON bytes (XSIAM get returns a ZIP of YAML)."""
    if not data:
        raise PlaybookApiError("Empty playbook payload")
    raw = data
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            chosen = _zip_playbook_member(archive.namelist())
            raw = archive.read(chosen)
    text = raw.decode("utf-8")
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        loaded = json.loads(text)
    else:
        loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise PlaybookApiError(f"Playbook payload is not an object: {type(loaded)}")
    return normalize_playbook(loaded)


XSIAM_PACK_METADATA: JsonDict = {
    "id": "",
    "version": 0,
    "cacheVersn": 0,
    "modified": "0001-01-01T00:00:00Z",
    "sizeInBytes": 0,
    "packID": "",
    "packName": "",
    "itemVersion": "",
    "fromServerVersion": "",
    "toServerVersion": "",
    "definitionId": "",
    "isOverridable": False,
    "vcShouldIgnore": False,
    "vcShouldKeepItemLegacyProdMachine": False,
    "commitMessage": "",
    "shouldCommit": False,
    "currentVersion": "",
    "name": "",
    "description": "",
    "updated": "0001-01-01T00:00:00Z",
    "created": "0001-01-01T00:00:00Z",
    "support": "",
    "author": "",
    "authorImage": "",
    "supportDetails": {"url": "", "email": ""},
    "beta": False,
    "deprecated": False,
    "certification": "",
    "serverMinVersion": "",
    "serverMaxVersion": "",
    "general": None,
    "tags": None,
    "rawTags": None,
}


def _item_name_from_yaml(yaml_text: str, fallback: str) -> str:
    loaded = yaml.safe_load(yaml_text)
    if isinstance(loaded, dict):
        name = loaded.get("name") or loaded.get("id")
        if name:
            return str(name)
    stem = Path(fallback).stem
    return stem


def _xsiam_zip_member_path(content_kind: str, item_name: str) -> str:
    """XSIAM insert expects pack-style ZIP members (see scripts/get and playbooks/get)."""
    if content_kind == "script":
        return f"automation/automation-{item_name}.yml"
    if content_kind == "playbook":
        stem = item_name.replace(" ", "_").replace("/", "_")
        return f"playbook/playbook-{stem}.yml"
    raise ValueError(f"Unsupported XSIAM content kind: {content_kind!r}")


def xsiam_content_zip_bytes(
    yaml_text: str,
    *,
    content_kind: str,
    item_name: Optional[str] = None,
    filename: str = "item.yml",
) -> bytes:
    resolved_name = item_name or _item_name_from_yaml(yaml_text, filename)
    member = _xsiam_zip_member_path(content_kind, resolved_name)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("metadata.json", json.dumps(XSIAM_PACK_METADATA))
        archive.writestr(member, yaml_text.encode("utf-8"))
    return buffer.getvalue()


def yaml_to_zip_bytes(yaml_text: str, filename: str = "playbook.yml") -> bytes:
    """Legacy flat ZIP (YAML at archive root). Prefer ``xsiam_content_zip_bytes`` for XSIAM."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(filename, yaml_text.encode("utf-8"))
    return buffer.getvalue()


class PlaybookClient:
    def __init__(self, credentials: Credentials, *, timeout: float = 120.0):
        self.credentials = credentials
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Authorization": credentials.key})
        if credentials.platform.requires_auth_id():
            if not credentials.api_id:
                raise PlaybookApiError(f"{credentials.platform.value} credentials require 'id' (x-xdr-auth-id)")
            self.session.headers["x-xdr-auth-id"] = str(credentials.api_id)
        elif credentials.api_id:
            self.session.headers["x-xdr-auth-id"] = str(credentials.api_id)
        self.session.verify = credentials.verify_ssl
        if not credentials.verify_ssl:
            try:
                import urllib3

                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            except Exception:
                pass

    def api_prefix(self) -> str:
        if self.credentials.platform == Platform.XSOAR8:
            return "/xsoar/public/v1"
        if self.credentials.platform == Platform.XSIAM:
            return "/public_api/v1"
        return ""

    def url(self, path: str) -> str:
        path = path if path.startswith("/") else f"/{path}"
        return f"{self.credentials.host}{self.api_prefix()}{path}"

    def _raise_for_status(self, response: requests.Response, action: str) -> None:
        if response.ok:
            return
        body: Any
        try:
            body = response.json()
        except Exception:
            body = response.text[:2000]
        raise PlaybookApiError(
            f"{action} failed: HTTP {response.status_code} {body!r}",
            status_code=response.status_code,
            body=body,
        )

    def playbook_search_url(self) -> str:
        """Bulk list. XSIAM has no public_api search; use the XSOAR-compat path."""
        if self.credentials.platform == Platform.XSIAM:
            return f"{self.credentials.host}/xsoar/public/v1/playbook/search"
        return self.url("/playbook/search")

    def search_playbooks(self, query: Optional[str] = None) -> JsonDict:
        payload: JsonDict = {}
        if query:
            payload["query"] = query
        # XSOAR 6: POST /playbook/search
        # XSOAR 8 / XSIAM: POST /xsoar/public/v1/playbook/search
        # XSIAM official docs only list get/insert/delete; lab search takes ~30s and ~40MB.
        timeout = max(self.timeout, 300.0) if self.credentials.platform == Platform.XSIAM else self.timeout
        response = self.session.post(
            self.playbook_search_url(),
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
            allow_redirects=False,
        )
        self._raise_for_status(response, "playbook search")
        data = response.json()
        if not isinstance(data, dict):
            raise PlaybookApiError(f"playbook search returned non-object: {type(data)}")
        return data

    def get_playbook(self, playbook_id: str) -> JsonDict:
        with timed_operation("Download playbook %s", playbook_id):
            if self.credentials.platform == Platform.XSIAM:
                return self._xsiam_get(field="id", value=playbook_id)

            encoded = quote(str(playbook_id), safe="")
            # XSOAR 6: GET /playbook/{id} (not always present; fall back to search)
            # XSOAR 8: GET /xsoar/public/v1/playbook/{id}
            response = self.session.get(self.url(f"/playbook/{encoded}"), timeout=self.timeout)
            if response.status_code == 404 and self.credentials.platform == Platform.XSOAR6:
                return self._get_from_search(playbook_id)
            self._raise_for_status(response, f"get playbook {playbook_id}")
            data = response.json()
            if not isinstance(data, dict):
                raise PlaybookApiError(f"get playbook returned non-object: {type(data)}")
            if "playbook" in data and isinstance(data["playbook"], dict) and "tasks" not in data:
                return normalize_playbook(data["playbook"])
            return normalize_playbook(data)

    def get_playbook_by_name(self, name: str) -> JsonDict:
        with timed_operation("Download playbook %s", name):
            if self.credentials.platform == Platform.XSIAM:
                return self._xsiam_get(field="name", value=name)
            results = self.search_playbooks()
            matches = [
                item
                for item in (results.get("playbooks") or [])
                if isinstance(item, dict) and str(item.get("name") or "") == name
            ]
            if len(matches) == 1:
                return normalize_playbook(matches[0])
            if len(matches) > 1:
                raise PlaybookApiError(f"Playbook name {name!r} is ambiguous ({len(matches)} matches)")
            raise PlaybookApiError(f"Playbook name {name!r} not found", status_code=404)

    def _xsiam_get(self, *, field: str, value: str) -> JsonDict:
        payload = {"request_data": {"filter": {"field": field, "value": value}}}
        response = self.session.post(
            self.url("/playbooks/get"),
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        self._raise_for_status(response, f"XSIAM playbooks/get field={field}")
        return decode_playbook_payload(response.content)

    def get_script_yaml(self, *, script_id: Optional[str] = None, name: Optional[str] = None) -> str:
        """Download one automation script YAML from XSIAM (``POST /scripts/get``)."""
        if self.credentials.platform != Platform.XSIAM:
            raise UnsupportedOnTenant("get_script_yaml is only supported on XSIAM")
        if bool(script_id) == bool(name):
            raise PlaybookApiError("get_script_yaml requires exactly one of script_id or name")
        field, value = ("id", script_id) if script_id else ("name", name)
        label = f"Download script {value} ({field})"
        with timed_operation(label):
            payload = {"request_data": {"filter": {"field": field, "value": value}}}
            response = self.session.post(
                self.url("/scripts/get"),
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )
            self._raise_for_status(response, f"XSIAM scripts/get field={field}")
            return decode_script_yaml_payload(response.content)

    def xsiam_script_exists(self, name: str) -> bool:
        if self.credentials.platform != Platform.XSIAM:
            return False
        payload = {"request_data": {"filter": {"field": "name", "value": name}}}
        response = self.session.post(
            self.url("/scripts/get"),
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        return response.ok and response.content[:2] == b"PK"

    def _get_from_search(self, playbook_id: str) -> JsonDict:
        results = self.search_playbooks()
        for item in results.get("playbooks") or []:
            if isinstance(item, dict) and str(item.get("id")) == str(playbook_id):
                return normalize_playbook(item)
        raise PlaybookApiError(f"Playbook {playbook_id!r} not found in search results", status_code=404)

    def search_scripts(self) -> List[JsonDict]:
        """Return automation search hits. Empty on XSIAM (no bulk automation search here)."""
        if self.credentials.platform == Platform.XSIAM:
            return []
        response = self.session.post(
            self.url("/automation/search"),
            json={},
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        self._raise_for_status(response, "automation search")
        data = response.json()
        if not isinstance(data, dict):
            raise PlaybookApiError(f"automation search returned non-object: {type(data)}")
        scripts = data.get("scripts") or []
        return [item for item in scripts if isinstance(item, dict)]

    def script_id_to_name(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for script in self.search_scripts():
            sid = str(script.get("id") or "")
            name = str(script.get("name") or "")
            if sid and name:
                mapping[sid] = name
        return mapping

    def _multipart_headers(self) -> dict[str, str]:
        return {k: v for k, v in self.session.headers.items() if k.lower() != "content-type"}

    def _post_yaml_file(self, endpoint: str, yaml_text: str, filename: str, *, action: str) -> JsonDict:
        response = self.session.post(
            self.url(endpoint),
            files={"file": (filename, yaml_text.encode("utf-8"), "text/yaml")},
            headers=self._multipart_headers(),
            timeout=self.timeout,
        )
        self._raise_for_status(response, action)
        return _json_or_raw(response)

    def _post_yaml_zip(
        self,
        endpoint: str,
        yaml_text: str,
        filename: str,
        *,
        action: str,
        content_kind: str,
    ) -> JsonDict:
        item_name = _item_name_from_yaml(yaml_text, filename)
        zip_bytes = xsiam_content_zip_bytes(
            yaml_text,
            content_kind=content_kind,
            item_name=item_name,
            filename=filename,
        )
        zip_name = item_name.replace(" ", "_").replace("/", "_") + ".zip"
        response = self.session.post(
            self.url(endpoint),
            files={"file": (zip_name, zip_bytes, "application/zip")},
            headers=self._multipart_headers(),
            timeout=self.timeout,
        )
        self._raise_for_status(response, action)
        return _json_or_raw(response)

    def _xsiam_playbook_insert(self, yaml_text: str, filename: str) -> JsonDict:
        """Insert/update a playbook on XSIAM, falling back to flat ZIP when pack layout fails."""
        pack_result = self._post_yaml_zip(
            "/playbooks/insert",
            yaml_text,
            filename,
            action="XSIAM playbooks/insert",
            content_kind="playbook",
        )
        if not insert_failure_items(pack_result):
            return pack_result

        flat_bytes = yaml_to_zip_bytes(yaml_text, filename=filename)
        flat_name = Path(filename).stem.replace(" ", "_").replace("/", "_") + ".zip"
        response = self.session.post(
            self.url("/playbooks/insert"),
            files={"file": (flat_name, flat_bytes, "application/zip")},
            headers=self._multipart_headers(),
            timeout=self.timeout,
        )
        self._raise_for_status(response, "XSIAM playbooks/insert flat zip fallback")
        flat_result = _json_or_raw(response)
        if insert_failure_items(flat_result):
            return pack_result
        flat_result.setdefault("upload_mode", "flat_zip")
        return flat_result

    def save_yaml(self, yaml_text: str, filename: str = "playbook.yml") -> JsonDict:
        """Upload or update a playbook from YAML.

        XSOAR 6: ``POST /playbook/save/yaml``
        XSOAR 8: ``POST /xsoar/public/v1/playbook/save/yaml``
        XSIAM: ``POST /public_api/v1/playbooks/insert`` (YAML inside ZIP)
        """
        with timed_operation("Upload playbook %s", filename):
            if self.credentials.platform == Platform.XSIAM:
                return self._xsiam_playbook_insert(yaml_text, filename)
            return self._post_yaml_file("/playbook/save/yaml", yaml_text, filename, action="playbook save yaml")

    def save_script_yaml(self, yaml_text: str, filename: str = "script.yml") -> JsonDict:
        """Upload or update an automation script from YAML.

        XSOAR 6: ``POST /automation/import`` (multipart YAML)
        XSOAR 8: ``POST /xsoar/public/v1/automation`` (JSON wrapper around parsed YAML)
        XSIAM: ``POST /public_api/v1/scripts/insert`` (YAML inside ZIP)
        """
        with timed_operation("Upload script %s", filename):
            platform = self.credentials.platform
            if platform == Platform.XSIAM:
                return self._post_yaml_zip(
                    "/scripts/insert",
                    yaml_text,
                    filename,
                    action="XSIAM scripts/insert",
                    content_kind="script",
                )
            if platform == Platform.XSOAR6:
                return self._post_yaml_file("/automation/import", yaml_text, filename, action="automation import")

            loaded = yaml.safe_load(yaml_text)
            if not isinstance(loaded, dict):
                raise PlaybookApiError(f"Script YAML must deserialize to an object: {filename}")
            payload: JsonDict = {
                "savePassword": bool(str(loaded.get("pswd") or "").strip()),
                "script": loaded,
            }
            json_headers = dict(self.session.headers)
            json_headers["Content-Type"] = "application/json"
            response = self.session.post(
                self.url("/automation"),
                json=payload,
                headers=json_headers,
                timeout=self.timeout,
            )
            if response.status_code == 409:
                body = _json_or_raw(response)
                if isinstance(body, dict):
                    body.setdefault("http_status", 409)
                return body
            self._raise_for_status(response, "automation save json")
            return _json_or_raw(response)

    def delete_playbook(self, *, playbook_id: Optional[str] = None, name: Optional[str] = None) -> JsonDict:
        """Delete one playbook by id (preferred) or unique name.

        XSOAR 6: POST /playbook/delete  body {"id": "<id>"}
        XSOAR 8: POST /xsoar/playbook/delete  body {"id": "<id>"}
                 Not under /xsoar/public/v1 — that prefix maps /playbook/delete onto
                 GET /playbook/{playbook_id} (id="delete") and returns 405.
        XSIAM:   POST /public_api/v1/playbooks/delete  body request_data.filter
                 https://cortex-docs.paloaltonetworks.com/xsiam-api/cortex-platform/playbooks
        """
        if not playbook_id and not name:
            raise PlaybookApiError("delete_playbook requires playbook_id or name")

        headers = {"Content-Type": "application/json"}
        if self.credentials.platform == Platform.XSIAM:
            field, value = ("id", playbook_id) if playbook_id else ("name", name)
            payload = {"request_data": {"filter": {"field": field, "value": value}}}
            response = self.session.post(
                self.url("/playbooks/delete"),
                json=payload,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=False,
            )
            self._raise_for_status(response, "XSIAM playbooks/delete")
            return _json_or_raw(response)

        resolved_id = playbook_id
        resolved_name = name
        if not resolved_id:
            found = self.get_playbook_by_name(str(name))
            resolved_id = str(found.get("id") or "")
            resolved_name = resolved_name or str(found.get("name") or "")
            if not resolved_id:
                raise PlaybookApiError(f"Playbook name {name!r} has no id")

        payload: JsonDict = {"id": resolved_id}
        if resolved_name:
            payload["name"] = resolved_name

        if self.credentials.platform == Platform.XSOAR8:
            delete_url = f"{self.credentials.host}/xsoar/playbook/delete"
        else:
            delete_url = self.url("/playbook/delete")
        response = self.session.post(
            delete_url,
            json=payload,
            headers=headers,
            timeout=self.timeout,
            allow_redirects=False,
        )
        self._raise_for_status(response, f"playbook delete {resolved_id}")
        result = _json_or_raw(response)
        result.setdefault("id", resolved_id)
        return result


def _json_or_raw(response: requests.Response) -> JsonDict:
    if not response.content:
        return {}
    try:
        data = response.json()
    except json.JSONDecodeError:
        return {"raw": response.text}
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        return {"status": data}
    return {"raw": data}


def insert_failure_items(upload_response: Mapping[str, Any]) -> List[JsonDict]:
    """XSIAM insert/delete style ``failures_items`` when nothing succeeded."""
    objects = upload_response.get("objects")
    if not isinstance(objects, dict):
        return []
    if objects.get("succeeded_items"):
        return []
    failures = objects.get("failures_items") or []
    return [item for item in failures if isinstance(item, dict)]


def unwrap_saved_playbook(upload_response: Mapping[str, Any]) -> Optional[JsonDict]:
    playbook = upload_response.get("playbook")
    if isinstance(playbook, dict):
        return playbook
    objects = upload_response.get("objects")
    if isinstance(objects, dict):
        items = objects.get("succeeded_items") or []
        if isinstance(items, list) and len(items) == 1 and isinstance(items[0], dict):
            item_id = items[0].get("id")
            if item_id:
                out: JsonDict = {"id": str(item_id)}
                if items[0].get("name"):
                    out["name"] = items[0]["name"]
                return out
    return None
