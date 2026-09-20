from __future__ import annotations

from cortex_ps_toolkit.core.paths import (
    api_keys_delete_url,
    api_keys_generate_url,
    api_keys_get_url,
    biocs_delete_url,
    biocs_get_url,
    biocs_insert_url,
    classifier_search_url,
    content_bundle_import_url,
    incidentfield_delete_url,
    incidentfields_list_url,
    incidenttype_delete_url,
    incidenttype_list_url,
    incidenttype_write_url,
    indicators_batch_delete_url,
    indicators_delete_url,
    indicators_get_url,
    indicators_insert_url,
    layout_delete_url,
    layout_get_url,
    preprocess_rules_list_url,
    rbac_get_roles_url,
    rbac_get_user_group_url,
    rbac_get_users_url,
    rbac_set_user_role_url,
    uses_xsoar_webapp_prefix,
    xsoar_webapp_path,
    xsoar_webapp_url,
)
from cortex_ps_toolkit.platforms import Platform

HOST = "https://tenant.example.test"


def test_uses_xsoar_webapp_prefix() -> None:
    assert not uses_xsoar_webapp_prefix(Platform.XSOAR6)
    assert uses_xsoar_webapp_prefix(Platform.XSOAR8)
    assert uses_xsoar_webapp_prefix(Platform.XSIAM)


def test_xsoar_webapp_path_cloud() -> None:
    assert xsoar_webapp_path(Platform.XSOAR8, "/incidenttype") == "/xsoar/incidenttype"
    assert xsoar_webapp_path(Platform.XSIAM, "/xsoar/incidenttype") == "/xsoar/incidenttype"


def test_xsoar_webapp_path_xsoar6() -> None:
    assert xsoar_webapp_path(Platform.XSOAR6, "/incidenttype") == "/incidenttype"
    assert xsoar_webapp_path(Platform.XSOAR6, "/xsoar/incidenttype") == "/incidenttype"


def test_incidentfield_urls() -> None:
    assert (
        incidentfields_list_url(HOST, Platform.XSOAR8)
        == "https://tenant.example.test/xsoar/public/v1/incidentfields"
    )
    assert (
        incidentfields_list_url(HOST, Platform.XSOAR6)
        == "https://tenant.example.test/incidentfields"
    )
    assert (
        incidentfield_delete_url(HOST, Platform.XSOAR8, "incident_myfield")
        == "https://tenant.example.test/xsoar/incidentfield/incident_myfield"
    )
    assert (
        incidentfield_delete_url(HOST, Platform.XSOAR6, "incident_myfield")
        == "https://tenant.example.test/incidentfield/incident_myfield"
    )


def test_incidenttype_urls() -> None:
    assert (
        incidenttype_list_url(HOST, Platform.XSOAR8)
        == "https://tenant.example.test/xsoar/incidenttype"
    )
    assert (
        incidenttype_list_url(HOST, Platform.XSOAR6)
        == "https://tenant.example.test/incidenttype"
    )
    assert (
        incidenttype_write_url(HOST, Platform.XSOAR8)
        == "https://tenant.example.test/xsoar/public/v1/incidenttype"
    )
    assert (
        incidenttype_delete_url(HOST, Platform.XSOAR8)
        == "https://tenant.example.test/xsoar/incidenttype/delete"
    )
    assert (
        incidenttype_delete_url(HOST, Platform.XSOAR6)
        == "https://tenant.example.test/incidenttype/delete"
    )


def test_layouts_list_url() -> None:
    from cortex_ps_toolkit.core.paths import layouts_list_url

    assert (
        layouts_list_url(HOST, Platform.XSOAR8)
        == "https://tenant.example.test/xsoar/layouts"
    )
    assert (
        layouts_list_url(HOST, Platform.XSOAR6)
        == "https://tenant.example.test/layouts"
    )


def test_layout_urls_encode_spaces() -> None:
    layout_id = "AAAA - Test Layout"
    assert (
        layout_get_url(HOST, Platform.XSOAR8, layout_id)
        == "https://tenant.example.test/xsoar/layout/AAAA%20-%20Test%20Layout"
    )
    assert (
        layout_delete_url(HOST, Platform.XSOAR6, layout_id)
        == "https://tenant.example.test/layout/AAAA%20-%20Test%20Layout/remove"
    )


def test_classifier_and_preprocess_urls() -> None:
    assert (
        classifier_search_url(HOST, Platform.XSOAR8)
        == "https://tenant.example.test/xsoar/classifier/search"
    )
    assert (
        classifier_search_url(HOST, Platform.XSOAR6)
        == "https://tenant.example.test/classifier/search"
    )
    assert (
        preprocess_rules_list_url(HOST, Platform.XSIAM)
        == "https://tenant.example.test/xsoar/preprocess/rules"
    )
    assert (
        preprocess_rules_list_url(HOST, Platform.XSOAR6)
        == "https://tenant.example.test/preprocess/rules"
    )


def test_cortex_ui_webapp_urls() -> None:
    from cortex_ps_toolkit.core.paths import (
        parsing_rule_files_system_get_url,
        parsing_rule_files_user_get_url,
        xdm_mappings_files_system_get_url,
        xdm_mappings_files_user_get_url,
    )

    assert (
        parsing_rule_files_user_get_url(HOST)
        == "https://tenant.example.test/api/webapp/ingestion/xql/rule_files/user/get"
    )
    assert (
        xdm_mappings_files_user_get_url(HOST)
        == "https://tenant.example.test/api/webapp/xdm/xql/mappings_files/user/get"
    )
    assert (
        parsing_rule_files_system_get_url(HOST)
        == "https://tenant.example.test/api/webapp/ingestion/xql/rule_files/system/get"
    )
    assert (
        xdm_mappings_files_system_get_url(HOST)
        == "https://tenant.example.test/api/webapp/xdm/xql/mappings_files/system/get"
    )


def test_content_bundle_import_url() -> None:
    assert (
        content_bundle_import_url(HOST, Platform.XSIAM)
        == "https://tenant.example.test/xsoar/public/v1/content/bundle"
    )


def test_xsoar_webapp_url() -> None:
    assert (
        xsoar_webapp_url(HOST, Platform.XDR5, "/incidenttype/delete")
        == "https://tenant.example.test/xsoar/incidenttype/delete"
    )


def test_api_keys_public_api_urls() -> None:
    assert (
        api_keys_get_url(HOST)
        == "https://tenant.example.test/public_api/v1/api_keys/get_api_keys"
    )
    assert (
        api_keys_generate_url(HOST)
        == "https://tenant.example.test/public_api/v1/api_keys/generate"
    )
    assert (
        api_keys_delete_url(HOST)
        == "https://tenant.example.test/public_api/v1/api_keys/delete"
    )


def test_rbac_public_api_urls() -> None:
    assert (
        rbac_get_users_url(HOST)
        == "https://tenant.example.test/public_api/v1/rbac/get_users"
    )
    assert (
        rbac_get_roles_url(HOST)
        == "https://tenant.example.test/public_api/v1/rbac/get_roles"
    )
    assert (
        rbac_get_user_group_url(HOST)
        == "https://tenant.example.test/public_api/v1/rbac/get_user_group"
    )
    assert (
        rbac_set_user_role_url(HOST)
        == "https://tenant.example.test/public_api/v1/rbac/set_user_role"
    )


def test_indicators_public_api_urls() -> None:
    assert (
        indicators_get_url(HOST)
        == "https://tenant.example.test/public_api/v1/indicators/get"
    )
    assert (
        indicators_insert_url(HOST)
        == "https://tenant.example.test/public_api/v1/indicators/insert"
    )
    assert (
        indicators_delete_url(HOST)
        == "https://tenant.example.test/public_api/v1/indicators/delete"
    )


def test_biocs_public_api_urls() -> None:
    assert (
        biocs_get_url(HOST)
        == "https://tenant.example.test/public_api/v1/bioc/get"
    )
    assert (
        biocs_insert_url(HOST)
        == "https://tenant.example.test/public_api/v1/bioc/insert"
    )
    assert (
        biocs_delete_url(HOST)
        == "https://tenant.example.test/public_api/v1/bioc/delete"
    )


def test_indicators_batch_delete_url() -> None:
    assert (
        indicators_batch_delete_url(HOST, Platform.XSOAR6)
        == "https://tenant.example.test/indicators/batchDelete"
    )
    assert (
        indicators_batch_delete_url(HOST, Platform.XSOAR8)
        == "https://tenant.example.test/xsoar/public/v1/indicators/batchDelete"
    )
