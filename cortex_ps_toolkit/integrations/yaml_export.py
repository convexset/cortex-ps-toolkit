"""Export integration ModuleConfiguration JSON to demisto-style YAML."""

from __future__ import annotations

from typing import Any, Mapping

from ..content.yaml_codec import dumps_yaml
from .portable_yaml import configuration_to_portable_yaml_document_ordered


def configuration_to_yaml_document(configuration: Mapping[str, Any]) -> dict[str, Any]:
    return configuration_to_portable_yaml_document_ordered(configuration)


def configuration_to_yaml_text(configuration: Mapping[str, Any]) -> str:
    return dumps_yaml(configuration_to_yaml_document(configuration))
