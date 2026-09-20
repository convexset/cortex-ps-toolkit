"""HTTP client for Cortex tenant APIs (XSOAR 6/8, XSIAM compat paths)."""

from __future__ import annotations

from typing import Any, Mapping, Optional

import requests

from ..credentials import CredentialProfile
from ..platforms import Platform
from .paths import XSOAR_PUBLIC_V1_PREFIX, xsoar_shaped_path


class TenantApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class TenantClient:
    """Authenticated session scoped to one credential profile."""

    def __init__(self, profile: CredentialProfile, *, timeout: float = 120.0):
        self.profile = profile
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Authorization": profile.key})
        if profile.tenant_type.requires_auth_id():
            if not profile.api_id:
                raise TenantApiError(
                    f"{profile.tenant_type.value} credentials require api_id (x-xdr-auth-id header)"
                )
            self.session.headers["x-xdr-auth-id"] = str(profile.api_id)
        elif profile.api_id:
            self.session.headers["x-xdr-auth-id"] = str(profile.api_id)
        self.session.verify = profile.verify_ssl
        if not profile.verify_ssl:
            try:
                import urllib3

                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            except Exception:
                pass

    def api_prefix(self) -> str:
        if self.profile.tenant_type == Platform.XSOAR8:
            return XSOAR_PUBLIC_V1_PREFIX
        if self.profile.tenant_type == Platform.XSIAM:
            return "/public_api/v1"
        return ""

    def url(self, path: str) -> str:
        path = path if path.startswith("/") else f"/{path}"
        return f"{self.profile.host}{self.api_prefix()}{path}"

    def root_url(self, path: str) -> str:
        """Legacy XSOAR 6 root paths (e.g. ``/health``)."""
        path = path if path.startswith("/") else f"/{path}"
        return f"{self.profile.host}{path}"

    def public_api_url(self, path: str) -> str:
        """Cortex Platform ``/public_api/v1`` paths (XSOAR 8 system, XSIAM, XDR, AgentiX)."""
        path = path if path.startswith("/") else f"/{path}"
        if path.startswith("/public_api/"):
            return f"{self.profile.host}{path}"
        return f"{self.profile.host}/public_api/v1{path}"

    def xsoar_compat_url(self, path: str) -> str:
        """XSOAR-shaped URL under `/xsoar/public/v1` (XSIAM, XDR, AgentiX compat)."""
        return f"{self.profile.host}{xsoar_shaped_path(self.profile.tenant_type, path)}"

    def lists_base_path(self) -> str:
        """Lists API path — see `core/paths.py` and docs/PLATFORMS.md."""
        return xsoar_shaped_path(self.profile.tenant_type, "/lists")

    def lists_url(self, suffix: str = "") -> str:
        base = self.lists_base_path().rstrip("/")
        if not suffix:
            return f"{self.profile.host}{base}"
        suffix = suffix if suffix.startswith("/") else f"/{suffix}"
        return f"{self.profile.host}{base}{suffix}"

    def _raise_for_status(self, response: requests.Response, action: str) -> None:
        if response.ok:
            return
        body: Any
        try:
            body = response.json()
        except Exception:
            body = response.text[:2000]
        raise TenantApiError(
            f"{action} failed: HTTP {response.status_code} {body!r}",
            status_code=response.status_code,
            body=body,
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        action: str,
        json: Optional[Mapping[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> requests.Response:
        response = self.session.request(
            method.upper(),
            url,
            json=json,
            headers={"Content-Type": "application/json"} if json is not None else None,
            timeout=timeout or self.timeout,
            allow_redirects=False,
        )
        self._raise_for_status(response, action)
        return response

    @staticmethod
    def _response_json(response: requests.Response) -> Any:
        if not response.content:
            return None
        return response.json()

    def get_json(self, url: str, *, action: str, timeout: Optional[float] = None) -> Any:
        body, _status = self.get_json_with_status(url, action=action, timeout=timeout)
        return body

    def get_json_with_status(
        self,
        url: str,
        *,
        action: str,
        timeout: Optional[float] = None,
    ) -> tuple[Any, int]:
        response = self.request("GET", url, action=action, timeout=timeout)
        return self._response_json(response), response.status_code

    def post_json(
        self,
        url: str,
        *,
        action: str,
        payload: Optional[Mapping[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        body, _status = self.post_json_with_status(
            url,
            action=action,
            payload=payload,
            timeout=timeout,
        )
        return body

    def post_json_with_status(
        self,
        url: str,
        *,
        action: str,
        payload: Optional[Mapping[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> tuple[Any, int]:
        response = self.request("POST", url, action=action, json=payload, timeout=timeout)
        return self._response_json(response), response.status_code

    def post_multipart_with_status(
        self,
        url: str,
        *,
        action: str,
        files: Mapping[str, tuple[str, bytes, str]],
        timeout: Optional[float] = None,
    ) -> tuple[Any, int]:
        headers = {k: v for k, v in self.session.headers.items() if k.lower() != "content-type"}
        response = self.session.post(
            url,
            files=files,
            headers=headers,
            timeout=timeout or self.timeout,
            allow_redirects=False,
        )
        self._raise_for_status(response, action)
        return self._response_json(response), response.status_code

    def get_bytes(self, url: str, *, action: str, timeout: Optional[float] = None) -> bytes:
        response = self.request("GET", url, action=action, timeout=timeout)
        return response.content

    def post_bytes(self, url: str, *, action: str, payload: Optional[Mapping[str, Any]] = None) -> bytes:
        response = self.request("POST", url, action=action, json=payload)
        return response.content
