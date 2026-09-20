from __future__ import annotations

import gzip
import io
import json
import tarfile

from cortex_ps_toolkit.design_content.bundle import (
    build_bundle_gzip,
    bundle_member_name,
    derive_incident_field_cli_name,
    prepare_write_document,
    slug,
    strip_server_fields,
)


def test_slug_normalizes_spaces() -> None:
    assert slug("SampleMirror - Incoming Mapper") == "SampleMirror_-_Incoming_Mapper"


def test_derive_incident_field_cli_name() -> None:
    assert derive_incident_field_cli_name("SampleMirror Description") == "samplemirrorDescription"
    assert derive_incident_field_cli_name("SampleMirror Description-copy") == "samplemirrorDescriptionCopy"


def test_prepare_write_document_updates_cli_name_for_renamed_field() -> None:
    doc = prepare_write_document(
        {"id": "A", "name": "Field One", "cliName": "fieldOne"},
        new_id="Field One-copy",
        new_name="Field One-copy",
        asset="incident-fields",
    )
    assert doc["cliName"] == "fieldOneCopy"


def test_strip_server_fields_removes_version_metadata() -> None:
    doc = {"id": "A", "name": "A", "version": 3, "cacheVersn": 1, "details": {"x": 1}}
    stripped = strip_server_fields(doc)
    assert "version" not in stripped
    assert stripped["details"] == {"x": 1}


def test_bundle_member_names() -> None:
    assert bundle_member_name("layouts", {"name": "My Layout"}) == "/layoutscontainer-My_Layout.json"
    assert bundle_member_name("classifiers", {"name": "My Classifier"}) == "/classifier-My_Classifier.json"
    assert bundle_member_name(
        "preprocess",
        {"id": "abc-123", "name": "Rule One"},
    ) == "/preprocessrule-abc-123-Rule_One.json"


def test_build_bundle_gzip_contains_expected_members() -> None:
    layout = prepare_write_document({"id": "L1", "name": "L1", "version": 9}, new_id="L1", new_name="L1")
    classifier = prepare_write_document({"id": "C1", "name": "C1"}, new_id="C1", new_name="C1")
    payload = build_bundle_gzip([("layouts", layout), ("classifiers", classifier)])
    raw = gzip.decompress(payload)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        names = archive.getnames()
    assert "/layoutscontainer-L1.json" in names
    assert "/classifier-C1.json" in names
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        member = archive.extractfile("/layoutscontainer-L1.json")
        assert member is not None
        saved = json.loads(member.read().decode())
    assert saved["name"] == "L1"
    assert "version" not in saved
