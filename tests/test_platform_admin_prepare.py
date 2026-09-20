"""Tests for platform admin document preparation."""

from __future__ import annotations

from cortex_ps_toolkit.platform_admin.api import prepare_bioc_write, prepare_correlation_write


def test_prepare_correlation_write_strips_readonly_fields() -> None:
    source = {
        "name": "Original Rule",
        "alert_name": "Original Alert",
        "rule_id": "abc-123",
        "insert_time": 1,
        "modify_time": 2,
        "created_by": "admin",
        "hits": 99,
        "query": "dataset = x",
    }
    doc = prepare_correlation_write(source, new_name="Copied Rule")
    assert doc["name"] == "Copied Rule"
    assert doc["alert_name"] == "Copied Rule"
    assert "rule_id" not in doc
    assert "hits" not in doc
    assert doc["query"] == "dataset = x"


def test_prepare_bioc_write_strips_readonly_fields() -> None:
    source = {
        "name": "Original BIOC",
        "rule_id": 99,
        "type": "EXECUTION",
        "creation_time": 1,
        "modification_time": 2,
        "number_of_issues": 3,
        "source": "admin",
        "status": "enabled",
    }
    doc = prepare_bioc_write(source, new_name="Copied BIOC")
    assert doc["name"] == "Copied BIOC"
    assert "rule_id" not in doc
    assert "creation_time" not in doc
    assert "number_of_issues" not in doc
