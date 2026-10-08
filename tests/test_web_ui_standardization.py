"""Smoke tests for shared web UI helpers and shell asset wiring."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC = REPO_ROOT / "web" / "static"
BUILD_ID = "20261009h"


def _read_static(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_dom_utils_exports_shared_helpers() -> None:
    source = _read_static("dom-utils.js")
    for symbol in ("escapeHtml", "cptkGridHeight", "bindGridSelectionToolbar"):
        assert f"function {symbol}" in source
        assert f"window.{symbol} = {symbol}" in source


def test_panel_actions_exports_confirm_outcome_helpers() -> None:
    source = _read_static("panel-actions.js")
    for symbol in (
        "formatPreviewEntries",
        "showActionResult",
        "showActionOutcome",
        "summarizeGenericResult",
        "showActionError",
        "showActionSuccess",
    ):
        assert f"function {symbol}" in source
        assert f"window.{symbol} = {symbol}" in source


def test_content_viewer_render_includes_viewer_helpers() -> None:
    source = _read_static("content-viewer-render.js")
    for symbol in ("renderScriptOverview", "renderListOverview", "renderMarkdown"):
        assert f"function {symbol}" in source
    for symbol in ("renderTenantCredentialOverview", "renderPackOverview", "renderRawJsonSection"):
        assert f"function {symbol}" in source
        assert f"window.{symbol} = {symbol}" in source


def test_playbooks_panel_has_grid_selection_bar() -> None:
    html = _read_static("index.html")
    assert 'id="playbooks-selection-count" class="selection-count-badge"' in html
    assert 'id="playbooks-select-all-visible"' in html
    assert 'id="playbooks-select-none"' in html
    assert html.index("playbooks-select-all-visible") < html.index('id="playbooks-grid"')


def test_outcome_dialog_uses_shared_dialog_body_style() -> None:
    html = _read_static("index.html")
    assert 'id="outcome-dialog"' in html
    assert 'id="outcome-dialog-message" class="dialog-body"' in html


def test_index_html_loads_shared_helpers_with_unified_build_id() -> None:
    html = _read_static("index.html")
    assert f'dom-utils.js?v={BUILD_ID}' in html
    assert f'panel-actions.js?v={BUILD_ID}' in html
    assert f'content-viewer-render.js?v={BUILD_ID}' in html
    script_tags = re.findall(r'<script src="/static/[^"]+\.js\?v=([^"]+)"', html)
    assert script_tags
    assert len(set(script_tags)) == 1
    assert script_tags[0] == BUILD_ID


def test_deprecated_ui_modules_not_loaded_by_shell() -> None:
    html = _read_static("index.html")
    assert "design-content-ui.js" not in html
    assert "platform-admin-ui.js" not in html


def test_styles_define_grid_height_tokens() -> None:
    css = _read_static("styles.css")
    for token in ("--grid-height:", "--grid-height-compact:", "--grid-height-nested:"):
        assert token in css


def test_tabulator_utils_exports_analysis_and_column_helpers() -> None:
    source = _read_static("tabulator-utils.js")
    for symbol in ("cptkEnhanceColumns", "hydrateAnalysisTables", "renderAnalysisTableMountHtml"):
        assert f"function {symbol}" in source
        assert f"window.{symbol} = {symbol}" in source


def test_grid_search_supports_all_column_filtering() -> None:
    source = _read_static("grid-search.js")
    assert "function rowMatchesSearchFields" in source
    assert 'searchFields = "all"' in source


def test_copy_mode_controls_include_help_icons() -> None:
    source = _read_static("operation-ui.js")
    assert "function fieldHelpIcon" in source
    assert 'value="copy_as_new"' in source
    assert "Alternative to skip or overwrite when names collide" in source
    assert "field-help-icon" in source
    css = _read_static("styles.css")
    assert ".field-help-icon" in css


def test_operation_ui_exports_confirm_helpers() -> None:
    source = _read_static("operation-ui.js")
    for symbol in (
        "normalizeConfirmPlan",
        "confirmDeletePlan",
        "openRenameMapEditor",
        "scheduleCopyNameCheck",
        "confirmCopyPlan",
        "confirmOperation",
        "renderOperationPlan",
    ):
        assert f"window.{symbol} = {symbol}" in source
    assert "function planPreviewBody" in source


def test_analysis_fetch_ui_exports_notify_helpers() -> None:
    html = _read_static("index.html")
    assert f'analysis-fetch-ui.js?v={BUILD_ID}' in html
    source = _read_static("analysis-fetch-ui.js")
    for symbol in ("notifyAnalysisFetchPlan", "runPlaybookAnalysisJob"):
        assert f"function {symbol}" in source
        assert f"window.{symbol} = {symbol}" in source
