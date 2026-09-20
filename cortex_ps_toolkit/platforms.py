"""Platform taxonomy, API documentation links, and operation support matrix."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet, Iterable, Mapping, Optional, Sequence


class Platform(str, Enum):
    XSOAR6 = "xsoar6"
    XSOAR8 = "xsoar8"
    XSIAM = "xsiam"
    XDR3 = "xdr3"
    XDR5 = "xdr5"
    AGENTIX = "agentix"

    def label(self) -> str:
        return _PLATFORM_LABELS[self]

    def requires_auth_id(self) -> bool:
        return self in {
            Platform.XSOAR8,
            Platform.XSIAM,
            Platform.XDR3,
            Platform.XDR5,
            Platform.AGENTIX,
        }

    def doc_overview_url(self) -> str:
        return PLATFORM_DOC_OVERVIEWS[self]


_PLATFORM_LABELS = {
    Platform.XSOAR6: "Cortex XSOAR 6",
    Platform.XSOAR8: "Cortex XSOAR 8",
    Platform.XSIAM: "Cortex XSIAM",
    Platform.XDR3: "Cortex XDR 3.x",
    Platform.XDR5: "Cortex XDR 5.x",
    Platform.AGENTIX: "Cortex AgentiX",
}

PLATFORM_DOC_OVERVIEWS: Mapping[Platform, str] = {
    Platform.XSOAR6: "https://cortex-docs.paloaltonetworks.com/xsoar-6-api/cortex-xsoar-6.x-apis/cortex-xsoar-6-apis-overview",
    Platform.XSOAR8: "https://cortex-docs.paloaltonetworks.com/xsoar-8-api/cortex-xsoar-8.x-apis/cortex-xsoar-8-apis-overview",
    Platform.XSIAM: "https://cortex-docs.paloaltonetworks.com/xsiam-api",
    Platform.XDR3: "https://cortex-docs.paloaltonetworks.com/xdr-3-api",
    Platform.XDR5: "https://cortex-docs.paloaltonetworks.com/xdr-5-api",
    Platform.AGENTIX: "https://cortex-docs.paloaltonetworks.com/agentix-api",
}


def parse_platform(value: str) -> Platform:
    text = value.strip().lower().replace("-", "")
    aliases = {
        "xsoar6": Platform.XSOAR6,
        "6": Platform.XSOAR6,
        "xsoar8": Platform.XSOAR8,
        "8": Platform.XSOAR8,
        "xsiam": Platform.XSIAM,
        "xdr3": Platform.XDR3,
        "xdr5": Platform.XDR5,
        "agentix": Platform.AGENTIX,
    }
    if text not in aliases:
        supported = ", ".join(sorted({item.value for item in Platform}))
        raise ValueError(f"Unknown platform {value!r}; use one of: {supported}")
    return aliases[text]


def detect_platform(url: str, explicit: Optional[str] = None) -> Platform:
    if explicit:
        return parse_platform(explicit)
    host = url.lower()
    if "agentix" in host:
        return Platform.AGENTIX
    if "xsiam" in host:
        return Platform.XSIAM
    if "crtx." in host:
        return Platform.XSOAR8
    if ".xdr." in host:
        # XDR and XSIAM share the xdr host pattern — default to XSIAM unless caller sets tenant_type.
        return Platform.XSIAM
    return Platform.XSOAR6


class SupportLevel(str, Enum):
    DOCUMENTED = "documented"
    EXPERIMENTAL = "experimental"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class OperationSpec:
    """Platform support for one toolkit operation."""

    operation_id: str
    name: str
    documented: FrozenSet[Platform] = field(default_factory=frozenset)
    experimental: FrozenSet[Platform] = field(default_factory=frozenset)
    notes: str = ""

    def support_level(self, platform: Platform) -> SupportLevel:
        if platform in self.documented:
            return SupportLevel.DOCUMENTED
        if platform in self.experimental:
            return SupportLevel.EXPERIMENTAL
        return SupportLevel.UNSUPPORTED

    def is_available(self, platform: Platform) -> bool:
        return self.support_level(platform) != SupportLevel.UNSUPPORTED

    def supported_platforms(self) -> FrozenSet[Platform]:
        return self.documented | self.experimental


def _op(
    operation_id: str,
    name: str,
    *,
    documented: Sequence[Platform] = (),
    experimental: Sequence[Platform] = (),
    notes: str = "",
) -> OperationSpec:
    overlap = set(documented) & set(experimental)
    if overlap:
        raise ValueError(f"{operation_id}: platform cannot be both documented and experimental: {overlap}")
    return OperationSpec(
        operation_id=operation_id,
        name=name,
        documented=frozenset(documented),
        experimental=frozenset(experimental),
        notes=notes,
    )


# Registry — extend as features are implemented. See docs/PLATFORMS.md for rationale.
OPERATIONS: Mapping[str, OperationSpec] = {
    op.operation_id: op
    for op in (
        _op(
            "credentials.validate",
            "Validate credential profile",
            documented=tuple(Platform),
            notes=(
                "System-management endpoints per platform: XSOAR 6 /health* + workers; "
                "XSOAR 8 system_diagnostics/data/papi + healthcheck + get_tenant_info; "
                "XSIAM/XDR/AgentiX healthcheck + get_tenant_info."
            ),
        ),
        _op(
            "cache.playbooks.refresh",
            "Refresh playbook cache",
            documented=(Platform.XSOAR6, Platform.XSOAR8, Platform.XSIAM),
            experimental=(Platform.XDR3, Platform.XDR5, Platform.AGENTIX),
            notes=(
                "POST /playbook/search (XSOAR 6 legacy path) or /xsoar/public/v1/playbook/search. "
                "XSIAM/XDR/AgentiX use XSOAR compat search (lab-verified 2026-09-17)."
            ),
        ),
        _op(
            "cache.scripts.refresh",
            "Refresh automation/script cache",
            documented=(Platform.XSOAR6, Platform.XSOAR8, Platform.XSIAM),
            experimental=(Platform.XDR3, Platform.XDR5, Platform.AGENTIX),
            notes=(
                "XSOAR 6/8: POST /automation/search. "
                "XSIAM/XDR/AgentiX: experimental POST /xsoar/public/v1/automation/search compat; "
                "falls back with warning if unavailable."
            ),
        ),
        _op(
            "playbooks.list",
            "List playbooks from cache",
            documented=(Platform.XSOAR6, Platform.XSOAR8, Platform.XSIAM),
        ),
        _op(
            "playbooks.metrics",
            "Playbook exploded metrics",
            documented=(Platform.XSOAR6, Platform.XSOAR8, Platform.XSIAM),
        ),
        _op(
            "playbooks.refactor.extract_multi",
            "Refactor playbooks (extract-multi)",
            documented=(Platform.XSOAR6, Platform.XSOAR8, Platform.XSIAM),
            notes=(
                "Wraps bay/playbook-utils extract-multi: leaf/cluster subs, compare, "
                "post-task updates, refactor descriptions, parent copy upload."
            ),
        ),
        _op(
            "playbooks.refactor.update_tasks",
            "Update playbook task error-handling / context sharing",
            documented=(Platform.XSOAR6, Platform.XSOAR8, Platform.XSIAM),
            notes="Wraps bay/playbook-utils update-playbook-tasks (in-place overwrite).",
        ),
        _op(
            "playbooks.copy",
            "Copy playbooks to another tenant",
            documented=(Platform.XSOAR6, Platform.XSOAR8, Platform.XSIAM),
            experimental=(Platform.XDR3, Platform.XDR5, Platform.AGENTIX),
            notes=(
                "XDR/AgentiX: documented /public_api/v1/playbooks/* (zip get/insert; same shape as XSIAM). "
                "Cache refresh still uses compat /xsoar/public/v1/playbook/search."
            ),
        ),
        _op(
            "scripts.copy",
            "Copy scripts to another tenant",
            documented=(Platform.XSOAR6, Platform.XSOAR8, Platform.XSIAM),
            experimental=(Platform.XDR3, Platform.XDR5, Platform.AGENTIX),
            notes=(
                "XDR/AgentiX: documented /public_api/v1/scripts/* (zip get/insert; same shape as XSIAM)."
            ),
        ),
        _op(
            "xql.run",
            "Run XQL query (start/poll/stream)",
            documented=(Platform.XSIAM, Platform.XDR3, Platform.XDR5),
            experimental=(Platform.AGENTIX,),
            notes="Uses public_api/v1/xql on XSIAM/XDR tenants. Not available on classic XSOAR 6/8.",
        ),
        _op(
            "content.correlation_rules.list",
            "Correlation rules list/copy/delete via /public_api/v1/correlations/*",
            documented=(Platform.XSIAM, Platform.XDR5),
            experimental=(Platform.AGENTIX,),
            notes="Not on xsoar6/xsoar8. AgentiX documented; lab may return 402 without license.",
        ),
        _op(
            "content.biocs.manage",
            "BIOCs list/insert/delete via /public_api/v1/bioc/*",
            documented=(Platform.XSIAM, Platform.XDR5),
            experimental=(Platform.AGENTIX,),
            notes=(
                "XSIAM/XDR 5 Cortex Platform API. Filter delete by name (EQ). "
                "Not on xsoar6/xsoar8. AgentiX documented; lab may return 402 without license."
            ),
        ),
        _op(
            "content.widgets.list",
            "List dashboard widgets",
            documented=(Platform.XSOAR6, Platform.XSOAR8),
            experimental=(Platform.XSIAM,),
        ),
        _op(
            "cache.integrations.commands.refresh",
            "Refresh integration definitions cache",
            documented=(
                Platform.XSOAR6,
                Platform.XSOAR8,
                Platform.XSIAM,
                Platform.XDR5,
                Platform.AGENTIX,
            ),
            experimental=(Platform.XDR3,),
            notes=(
                "GET /settings/integration-commands (XSOAR6 legacy path strip). "
                "Lab-verified 2026-09-18 on xsoar-japac-dev, personal-xsoar6, psojapac-xsiam, "
                "cortex-cs-xdr5, cortex-cs-agentix."
            ),
        ),
        _op(
            "cache.integrations.instances.refresh",
            "Refresh integration instances cache",
            documented=(
                Platform.XSOAR6,
                Platform.XSOAR8,
                Platform.XSIAM,
                Platform.XDR5,
                Platform.AGENTIX,
            ),
            experimental=(Platform.XDR3,),
            notes=(
                "POST /settings/integration/search; secrets stripped before cache. "
                "Responses are large (4–66 MB on lab tenants)."
            ),
        ),
        _op(
            "cache.credentials.refresh",
            "Refresh tenant credentials metadata cache",
            documented=(
                Platform.XSOAR6,
                Platform.XSOAR8,
                Platform.XSIAM,
                Platform.XDR5,
                Platform.AGENTIX,
            ),
            experimental=(Platform.XDR3,),
            notes="POST /settings/credentials returns metadata only (no password/certificate values).",
        ),
        _op(
            "cache.contentpacks.refresh",
            "Refresh installed content packs cache",
            documented=(
                Platform.XSOAR6,
                Platform.XSOAR8,
                Platform.XSIAM,
                Platform.XDR5,
                Platform.AGENTIX,
            ),
            experimental=(Platform.XDR3,),
            notes="GET /contentpacks/metadata/installed (XSOAR-shaped path).",
        ),
        _op(
            "integrations.copy",
            "Copy custom integration definitions to another tenant",
            documented=(
                Platform.XSOAR6,
                Platform.XSOAR8,
                Platform.XSIAM,
                Platform.XDR5,
                Platform.AGENTIX,
            ),
            experimental=(Platform.XDR3,),
            notes=(
                "Read configurations[] from integration/search; upload YAML via "
                "integration-conf/upload (xsoar6 legacy path; xsoar8+ web-app /xsoar/settings/...)."
            ),
        ),
        _op(
            "integrations.delete",
            "Delete custom integration definitions",
            documented=(
                Platform.XSOAR6,
                Platform.XSOAR8,
                Platform.XSIAM,
                Platform.XDR5,
                Platform.AGENTIX,
            ),
            experimental=(Platform.XDR3,),
            notes=(
                "POST integration-conf/delete with full ModuleConfiguration body from integration/search. "
                "Warn when instances exist for the integration brand."
            ),
        ),
        _op(
            "vault.manage",
            "Local encrypted integration credential vault",
            documented=tuple(Platform),
            notes="Server-side VMK vault with alias passphrase wrap slots; independent of tenant APIs.",
        ),
        _op(
            "content.lists.manage",
            "Lists cache refresh and CRUD",
            documented=(Platform.XSOAR6, Platform.XSOAR8),
            experimental=(Platform.XSIAM, Platform.XDR3, Platform.XDR5, Platform.AGENTIX),
            notes=(
                "XSOAR 8: /xsoar/public/v1/lists (documented). "
                "XSOAR 6: /lists (strip /xsoar/public/v1 prefix). "
                "XSIAM, xdr3, xdr5, AgentiX: /xsoar/public/v1/lists compat (experimental; xdr3≈xdr5)."
            ),
        ),
        _op(
            "content.layouts.manage",
            "Layouts list/read/copy (bundle or xsoar6 direct import)",
            documented=(Platform.XSOAR6, Platform.XSOAR8, Platform.XSIAM, Platform.XDR5, Platform.AGENTIX),
            notes="Write via POST /content/bundle; xsoar6 also supports POST /layouts/import. Delete xsoar6/xsoar8.",
        ),
        _op(
            "content.classifiers.manage",
            "Classifiers/mappers list/read/copy (bundle or xsoar6 direct import)",
            documented=(Platform.XSOAR6, Platform.XSOAR8, Platform.XSIAM, Platform.XDR5, Platform.AGENTIX),
            notes="Write via bundle; xsoar6 also POST /classifier/import. Delete xsoar6 only.",
        ),
        _op(
            "content.preprocess.manage",
            "Preprocess rules list/read/copy (bundle or xsoar6 direct POST)",
            documented=(Platform.XSOAR6, Platform.XSOAR8, Platform.XSIAM, Platform.XDR5, Platform.AGENTIX),
            notes="Write via bundle; xsoar6 also POST /preprocess/rule. Delete xsoar6 only.",
        ),
        _op(
            "content.incident_fields.manage",
            "Incident fields list/read/copy/delete (direct POST/DELETE)",
            documented=(Platform.XSOAR6, Platform.XSOAR8, Platform.XSIAM, Platform.XDR5, Platform.AGENTIX),
            notes="GET /incidentfields; POST shaped /incidentfield; DELETE /xsoar/incidentfield/{id} on cloud.",
        ),
        _op(
            "content.incident_types.manage",
            "Incident types list/read/copy/delete (direct POST)",
            documented=(Platform.XSOAR6, Platform.XSOAR8, Platform.XSIAM, Platform.XDR5, Platform.AGENTIX),
            notes="GET /xsoar/incidenttype; POST shaped /incidenttype; POST /xsoar/incidenttype/delete.",
        ),
        _op(
            "content.indicators.manage",
            "IOC list/insert/delete (public API on xsiam/xdr5; batchDelete on xsoar6/xsoar8)",
            documented=(Platform.XSIAM, Platform.XDR5, Platform.XSOAR6, Platform.XSOAR8),
            experimental=(Platform.AGENTIX,),
            notes=(
                "xsiam/xdr5: /public_api/v1/indicators/{get,insert,delete} with filter delete (rule_id IN). "
                "xsoar6/xsoar8: shaped POST /indicators/batchDelete — requires ids plus filter query id:\"…\" "
                "(ids-only payload returns 500). public_api delete on xsoar8 returns 402 (no XSIAM license)."
            ),
        ),
        _op(
            "system.rbac.read",
            "RBAC users, roles, groups via /public_api/v1/rbac/*",
            documented=(Platform.XSOAR8, Platform.XSIAM, Platform.XDR5, Platform.AGENTIX),
            notes="get_roles requires role_names derived from users.",
        ),
        _op(
            "system.api_keys.manage",
            "API key list/generate/delete via /public_api/v1/api_keys/*",
            documented=(Platform.XSOAR8, Platform.XSIAM, Platform.XDR5, Platform.AGENTIX),
            notes="xsoar8 get_api_keys works but is undocumented.",
        ),
    )
}


def get_operation(operation_id: str) -> OperationSpec:
    if operation_id not in OPERATIONS:
        raise KeyError(f"Unknown operation {operation_id!r}")
    return OPERATIONS[operation_id]


def assert_operation_supported(operation_id: str, platform: Platform) -> OperationSpec:
    spec = get_operation(operation_id)
    if not spec.is_available(platform):
        supported = ", ".join(sorted(item.value for item in spec.supported_platforms()) or ["none"])
        raise UnsupportedOperation(
            f"Operation {operation_id!r} is not supported on {platform.value} "
            f"(supported: {supported}). {spec.notes}".strip()
        )
    return spec


class UnsupportedOperation(RuntimeError):
    """Raised when an operation is invoked on an unsupported platform."""


def operations_for_platform(platform: Platform) -> list[OperationSpec]:
    return [spec for spec in OPERATIONS.values() if spec.is_available(platform)]


def format_operations_table(platforms: Iterable[Platform] | None = None) -> str:
    selected = list(platforms or Platform)
    header = ["Operation", "ID"] + [item.value for item in selected]
    rows = [header, ["-" * len(col) for col in header]]
    for spec in sorted(OPERATIONS.values(), key=lambda item: item.operation_id):
        row = [spec.name, spec.operation_id]
        for platform in selected:
            level = spec.support_level(platform)
            if level == SupportLevel.DOCUMENTED:
                row.append("doc")
            elif level == SupportLevel.EXPERIMENTAL:
                row.append("exp")
            else:
                row.append("-")
        rows.append(row)
    widths = [max(len(row[index]) for row in rows) for index in range(len(header))]
    lines = []
    for row in rows:
        lines.append("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)))
    return "\n".join(lines)
