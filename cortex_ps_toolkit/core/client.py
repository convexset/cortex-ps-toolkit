"""HTTP client for Cortex tenant APIs (XSOAR 6/8, XSIAM compat paths)."""

from __future__ import annotations

import time
from typing import Any, Mapping, Optional

import requests

from ..credentials import CredentialProfile
from ..ops_log import log_api_request, log_api_response, op_error, op_info, op_warn
from .quiet_api_failures import tenant_api_failure_toast_suppressed
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

    def _report_http_failure(self, action: str, *, elapsed_ms: int, status_code: int) -> None:
        if tenant_api_failure_toast_suppressed():
            op_warn(
                "%s — failed after %dms (HTTP %s); handled by caller",
                action,
                elapsed_ms,
                status_code,
                notify=False,
            )
            return
        op_error("%s — failed after %dms (HTTP %s)", action, elapsed_ms, status_code)

    def _raise_for_status(self, response: requests.Response, action: str) -> None:
        if response.ok:
            return
        body: Any
        try:
            body = response.json()
        except Exception:
            body = response.text[:2000]
        if not tenant_api_failure_toast_suppressed():
            op_error("%s failed: HTTP %s", action, response.status_code)
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
        verb = method.upper()
        started = time.monotonic()
        op_info("%s — started", action)
        log_api_request(verb, url, action, request=json)
        try:
            response = self.session.request(
                verb,
                url,
                json=json,
                headers={"Content-Type": "application/json"} if json is not None else None,
                timeout=timeout or self.timeout,
                allow_redirects=False,
            )
        except Exception:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            op_error("%s — failed after %dms", action, elapsed_ms)
            raise
        body_preview: Any = None
        if response.content:
            try:
                body_preview = response.json()
            except Exception:
                content_type = str(response.headers.get("Content-Type") or "").lower()
                if "json" in content_type or "text" in content_type or "xml" in content_type:
                    body_preview = response.text if response.text else None
                else:
                    body_preview = f"<binary response, {len(response.content)} bytes>"
        log_api_response(verb, url, action, response=body_preview, status_code=response.status_code)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if response.ok:
            op_info("%s — completed in %dms (HTTP %s)", action, elapsed_ms, response.status_code)
        else:
            self._report_http_failure(action, elapsed_ms=elapsed_ms, status_code=response.status_code)
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
        file_names = {key: meta[0] for key, meta in files.items()}
        started = time.monotonic()
        op_info("%s — started", action)
        log_api_request("POST", url, action, request={"multipart_files": file_names})
        headers = {k: v for k, v in self.session.headers.items() if k.lower() != "content-type"}
        try:
            response = self.session.post(
                url,
                files=files,
                headers=headers,
                timeout=timeout or self.timeout,
                allow_redirects=False,
            )
        except Exception:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            op_error("%s — failed after %dms", action, elapsed_ms)
            raise
        body_preview: Any = None
        if response.content:
            try:
                body_preview = response.json()
            except Exception:
                content_type = str(response.headers.get("Content-Type") or "").lower()
                if "json" in content_type or "text" in content_type or "xml" in content_type:
                    body_preview = response.text if response.text else None
                else:
                    body_preview = f"<binary response, {len(response.content)} bytes>"
        log_api_response("POST", url, action, response=body_preview, status_code=response.status_code)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if response.ok:
            op_info("%s — completed in %dms (HTTP %s)", action, elapsed_ms, response.status_code)
        else:
            self._report_http_failure(action, elapsed_ms=elapsed_ms, status_code=response.status_code)
        self._raise_for_status(response, action)
        return self._response_json(response), response.status_code

    def get_bytes(self, url: str, *, action: str, timeout: Optional[float] = None) -> bytes:
        response = self.request("GET", url, action=action, timeout=timeout)
        return response.content

    def post_bytes(self, url: str, *, action: str, payload: Optional[Mapping[str, Any]] = None) -> bytes:
        response = self.request("POST", url, action=action, json=payload)
        return response.content
