from __future__ import annotations

from pathlib import Path

import pytest

from playbook_utils.yaml_upload import collect_yaml_paths, read_yaml_upload


def test_collect_yaml_paths_from_files(tmp_path: Path) -> None:
    first = tmp_path / "a.yml"
    second = tmp_path / "b.yaml"
    first.write_text("name: A\n", encoding="utf-8")
    second.write_text("name: B\n", encoding="utf-8")
    assert collect_yaml_paths([str(first), str(second)]) == [first.resolve(), second.resolve()]


def test_collect_yaml_paths_from_directory(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (tmp_path / "root.yml").write_text("name: Root\n", encoding="utf-8")
    (nested / "child.yml").write_text("name: Child\n", encoding="utf-8")
    assert collect_yaml_paths([str(tmp_path)]) == [tmp_path / "root.yml"]
    assert collect_yaml_paths([str(tmp_path)], recursive=True) == [
        nested / "child.yml",
        tmp_path / "root.yml",
    ]


def test_read_yaml_upload_rejects_empty(tmp_path: Path) -> None:
    path = tmp_path / "empty.yml"
    path.write_text("   \n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_yaml_upload(path)
