"""Cross-platform API path resolution (documented vs compat)."""

from __future__ import annotations

from ..platforms import Platform

# Documented XSOAR 8 public API prefix (see Cortex XSOAR 8 API docs).
XSOAR_PUBLIC_V1_PREFIX = "/xsoar/public/v1"

# Cloud / hybrid tenants where XSOAR-shaped content APIs often work under the compat prefix
# even when not listed in that platform's primary API docs.
# **Assumption:** xdr3 behaves like xdr5 until a lab tenant proves otherwise.
XSOAR_COMPAT_PLATFORMS = frozenset({
    Platform.XSIAM,
    Platform.XDR3,
    Platform.XDR5,
    Platform.AGENTIX,
})

# Tenants whose documented script/playbook CRUD uses ``/public_api/v1/{scripts,playbooks}/*``
# (zip YAML get/insert; JSON delete) — same contract as XSIAM per Cortex Platform / AgentiX docs.
CORTEX_PLATFORM_CONTENT_API_PLATFORMS = frozenset({
    Platform.XSIAM,
    Platform.XDR3,
    Platform.XDR5,
    Platform.AGENTIX,
})


def uses_cortex_platform_content_api(platform: Platform) -> bool:
    """True when script/playbook get/insert/delete should use ``/public_api/v1/...``."""
    return platform in CORTEX_PLATFORM_CONTENT_API_PLATFORMS


def uses_xsoar_public_v1_compat(platform: Platform) -> bool:
    """True when the tenant should try `/xsoar/public/v1/...` for XSOAR-shaped APIs."""
    return platform in XSOAR_COMPAT_PLATFORMS or platform == Platform.XSOAR8


def xsoar_shaped_path(platform: Platform, suffix: str) -> str:
    """Resolve full path suffix for an XSOAR 8-documented endpoint.

    Rules (see docs/PLATFORMS.md § Compatibility paths):
    - **xsoar8**, **xsiam**, **xdr3**, **xdr5**, **agentix** → keep `/xsoar/public/v1` + suffix
    - **xsoar6** → strip `/xsoar/public/v1`; use legacy root path + suffix
    """
    suffix = suffix if suffix.startswith("/") else f"/{suffix}"
    if platform == Platform.XSOAR6:
        if suffix.startswith(XSOAR_PUBLIC_V1_PREFIX):
            suffix = suffix[len(XSOAR_PUBLIC_V1_PREFIX):] or "/"
        return suffix
    if uses_xsoar_public_v1_compat(platform):
        if suffix.startswith(XSOAR_PUBLIC_V1_PREFIX):
            return suffix
        return f"{XSOAR_PUBLIC_V1_PREFIX}{suffix}"
    raise ValueError(f"No XSOAR-shaped path rule for platform {platform.value}")


def xsoar_shaped_url(host: str, platform: Platform, suffix: str) -> str:
    return f"{host.rstrip('/')}{xsoar_shaped_path(platform, suffix)}"


# Host-root web-app API used by the XSOAR UI (API key + x-xdr-auth-id on cloud).
# Differs from ``xsoar_shaped_path`` — do not prepend ``/xsoar/public/v1`` here.
XSOAR_WEBAPP_PREFIX = "/xsoar"


def uses_xsoar_webapp_prefix(platform: Platform) -> bool:
    """True when design-time delete/list routes live under ``/xsoar/...`` at host root."""
    return platform != Platform.XSOAR6


def xsoar_webapp_path(platform: Platform, suffix: str) -> str:
    """Resolve host-root web-app path suffix (see docs/api-compat/content-probe.md).

    - **xsoar6** → legacy root (``/incidenttype``, ``/layout/{id}/remove``)
    - **xsoar8**, **xsiam**, **xdr3**, **xdr5**, **agentix** → ``/xsoar`` + suffix
    """
    suffix = suffix if suffix.startswith("/") else f"/{suffix}"
    if uses_xsoar_webapp_prefix(platform):
        if suffix.startswith(XSOAR_WEBAPP_PREFIX):
            return suffix
        return f"{XSOAR_WEBAPP_PREFIX}{suffix}"
    if suffix.startswith(XSOAR_WEBAPP_PREFIX):
        suffix = suffix[len(XSOAR_WEBAPP_PREFIX):] or "/"
    return suffix


def xsoar_webapp_url(host: str, platform: Platform, suffix: str) -> str:
    return f"{host.rstrip('/')}{xsoar_webapp_path(platform, suffix)}"


def incidentfields_list_url(host: str, platform: Platform) -> str:
    return xsoar_shaped_url(host, platform, "/incidentfields")


def incidentfield_write_url(host: str, platform: Platform) -> str:
    return xsoar_shaped_url(host, platform, "/incidentfield")


def incidentfield_delete_url(host: str, platform: Platform, field_id: str) -> str:
    from urllib.parse import quote

    encoded = quote(field_id, safe="")
    if uses_xsoar_webapp_prefix(platform):
        return f"{host.rstrip('/')}/xsoar/incidentfield/{encoded}"
    return xsoar_shaped_url(host, platform, f"/incidentfield/{encoded}")


def incidenttype_list_url(host: str, platform: Platform) -> str:
    return xsoar_webapp_url(host, platform, "/incidenttype")


def incidenttype_write_url(host: str, platform: Platform) -> str:
    return xsoar_shaped_url(host, platform, "/incidenttype")


def incidenttype_delete_url(host: str, platform: Platform) -> str:
    return xsoar_webapp_url(host, platform, "/incidenttype/delete")


def layouts_list_url(host: str, platform: Platform) -> str:
    return xsoar_webapp_url(host, platform, "/layouts")


def layout_get_url(host: str, platform: Platform, layout_id: str) -> str:
    from urllib.parse import quote

    encoded = quote(layout_id, safe="")
    return xsoar_webapp_url(host, platform, f"/layout/{encoded}")


def layout_delete_url(host: str, platform: Platform, layout_id: str) -> str:
    from urllib.parse import quote

    encoded = quote(layout_id, safe="")
    return xsoar_webapp_url(host, platform, f"/layout/{encoded}/remove")


def content_bundle_import_url(host: str, platform: Platform) -> str:
    return xsoar_shaped_url(host, platform, "/content/bundle")


def content_bundle_export_url(host: str, platform: Platform) -> str:
    return xsoar_shaped_url(host, platform, "/content/bundle")


def vc_uncommitted_url(host: str, platform: Platform) -> str:
    return xsoar_shaped_url(host, platform, "/vc/changes/uncommitted")


def classifier_search_url(host: str, platform: Platform) -> str:
    return xsoar_webapp_url(host, platform, "/classifier/search")


def preprocess_rules_list_url(host: str, platform: Platform) -> str:
    return xsoar_webapp_url(host, platform, "/preprocess/rules")


# Cortex UI session layer (`/api/webapp/...`). Lab probes (2026-09-20): API key + x-xdr-auth-id
# → HTTP 500 on xsiam/xdr5/agentix/xsoar8; xsoar6 → SPA HTML. Likely requires browser session.
# Documented here for capture when session auth or a public API becomes available.
CORTEX_UI_WEBAPP_PREFIX = "/api/webapp"

PARSING_RULE_FILES_USER_GET_PATH = f"{CORTEX_UI_WEBAPP_PREFIX}/ingestion/xql/rule_files/user/get"
PARSING_RULE_FILES_SYSTEM_GET_PATH = f"{CORTEX_UI_WEBAPP_PREFIX}/ingestion/xql/rule_files/system/get"
XDM_MAPPINGS_FILES_USER_GET_PATH = f"{CORTEX_UI_WEBAPP_PREFIX}/xdm/xql/mappings_files/user/get"
XDM_MAPPINGS_FILES_SYSTEM_GET_PATH = f"{CORTEX_UI_WEBAPP_PREFIX}/xdm/xql/mappings_files/system/get"


def cortex_ui_webapp_url(host: str, path: str) -> str:
    """Host-root Cortex UI web-app path (``/api/webapp/...``). Session auth expected."""
    path = path if path.startswith("/") else f"/{path}"
    return f"{host.rstrip('/')}{path}"


def parsing_rule_files_user_get_url(host: str) -> str:
    return cortex_ui_webapp_url(host, PARSING_RULE_FILES_USER_GET_PATH)


def parsing_rule_files_system_get_url(host: str) -> str:
    return cortex_ui_webapp_url(host, PARSING_RULE_FILES_SYSTEM_GET_PATH)


def xdm_mappings_files_user_get_url(host: str) -> str:
    return cortex_ui_webapp_url(host, XDM_MAPPINGS_FILES_USER_GET_PATH)


def xdm_mappings_files_system_get_url(host: str) -> str:
    return cortex_ui_webapp_url(host, XDM_MAPPINGS_FILES_SYSTEM_GET_PATH)


def indicators_get_url(host: str) -> str:
    return cortex_ui_webapp_url(host, "/public_api/v1/indicators/get")


def indicators_insert_url(host: str) -> str:
    return cortex_ui_webapp_url(host, "/public_api/v1/indicators/insert")


def indicators_delete_url(host: str) -> str:
    return cortex_ui_webapp_url(host, "/public_api/v1/indicators/delete")


def indicators_batch_delete_url(host: str, platform: Platform) -> str:
    """XSOAR 6/8 indicator delete via documented batchDelete (not Cortex Platform IOC API)."""
    return xsoar_shaped_url(host, platform, "/indicators/batchDelete")


def rbac_get_users_url(host: str) -> str:
    return cortex_ui_webapp_url(host, "/public_api/v1/rbac/get_users")


def rbac_get_roles_url(host: str) -> str:
    return cortex_ui_webapp_url(host, "/public_api/v1/rbac/get_roles")


def rbac_get_user_group_url(host: str) -> str:
    return cortex_ui_webapp_url(host, "/public_api/v1/rbac/get_user_group")


def rbac_set_user_role_url(host: str) -> str:
    return cortex_ui_webapp_url(host, "/public_api/v1/rbac/set_user_role")


def api_keys_get_url(host: str) -> str:
    return cortex_ui_webapp_url(host, "/public_api/v1/api_keys/get_api_keys")


def api_keys_generate_url(host: str) -> str:
    return cortex_ui_webapp_url(host, "/public_api/v1/api_keys/generate")


def api_keys_delete_url(host: str) -> str:
    return cortex_ui_webapp_url(host, "/public_api/v1/api_keys/delete")


def correlations_get_url(host: str) -> str:
    return cortex_ui_webapp_url(host, "/public_api/v1/correlations/get")


def correlations_insert_url(host: str) -> str:
    return cortex_ui_webapp_url(host, "/public_api/v1/correlations/insert")


def correlations_delete_url(host: str) -> str:
    return cortex_ui_webapp_url(host, "/public_api/v1/correlations/delete")


def biocs_get_url(host: str) -> str:
    return cortex_ui_webapp_url(host, "/public_api/v1/bioc/get")


def biocs_insert_url(host: str) -> str:
    return cortex_ui_webapp_url(host, "/public_api/v1/bioc/insert")


def biocs_delete_url(host: str) -> str:
    return cortex_ui_webapp_url(host, "/public_api/v1/bioc/delete")
