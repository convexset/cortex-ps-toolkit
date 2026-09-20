"""Design-time content asset kinds."""

from __future__ import annotations

from typing import Literal

AssetKind = Literal[
    "layouts",
    "classifiers",
    "preprocess",
    "incident-fields",
    "incident-types",
]

ASSET_KINDS: tuple[AssetKind, ...] = (
    "layouts",
    "classifiers",
    "preprocess",
    "incident-fields",
    "incident-types",
)

OPERATION_BY_ASSET: dict[AssetKind, str] = {
    "layouts": "content.layouts.manage",
    "classifiers": "content.classifiers.manage",
    "preprocess": "content.preprocess.manage",
    "incident-fields": "content.incident_fields.manage",
    "incident-types": "content.incident_types.manage",
}

# Cross-tenant workflow order (fields before layouts/types that reference them).
ORCHESTRATOR_ASSET_ORDER: tuple[AssetKind, ...] = (
    "incident-fields",
    "layouts",
    "incident-types",
    "classifiers",
    "preprocess",
)
