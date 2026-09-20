"""Minimal YAML encode/decode for playbook and script copy."""

from __future__ import annotations

import re
from typing import Any, Mapping

import yaml

# XSOAR exports may contain unquoted `simple: =` (condition operators) which
# strict PyYAML rejects as tag:yaml.org,2002:value.
_BARE_EQUALS = re.compile(r"(?m)^(\s+simple:\s*)=$")


def _sanitize_playbook_yaml(text: str) -> str:
    return _BARE_EQUALS.sub(r'\1"="', text)


def dumps_yaml(document: Mapping[str, Any]) -> str:
    return yaml.safe_dump(
        dict(document),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


def loads_yaml(text: str) -> dict[str, Any]:
    loaded = yaml.safe_load(_sanitize_playbook_yaml(text))
    if not isinstance(loaded, dict):
        raise ValueError(f"YAML must deserialize to an object, got {type(loaded)}")
    return loaded
