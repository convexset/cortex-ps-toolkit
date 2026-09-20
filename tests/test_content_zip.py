from __future__ import annotations

import zipfile
from io import BytesIO

from cortex_ps_toolkit.content.zip_payload import (
    decode_zip_yaml_payload,
    xsiam_content_zip_bytes,
)


def test_xsiam_content_zip_roundtrip() -> None:
    yaml_text = "name: Test PB\nid: abc\n"
    zipped = xsiam_content_zip_bytes(yaml_text, content_kind="playbook", filename="Test PB.yml")
    with zipfile.ZipFile(BytesIO(zipped)) as archive:
        names = archive.namelist()
        assert any(name.endswith(".yml") for name in names)
        assert "metadata.json" in names
    decoded = decode_zip_yaml_payload(zipped, content_kind="playbook")
    assert "name: Test PB" in decoded
