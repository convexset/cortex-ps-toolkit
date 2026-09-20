# Integration / Credentials / Content Packs API Compatibility Probe

Read-only probe of XSOAR-shaped settings and content-pack endpoints across lab tenant profiles.

**Probed:** 2026-09-18 (UTC)  
**Method:** `TenantClient` session + `xsoar_shaped_path()` from `cortex_ps_toolkit/core/paths.py`  
**Credentials:** `data/collections/credentials.json` (read-only; no modifications)

## Path routing

| Platform | Prefix rule |
| --- | --- |
| **xsoar8**, **xsiam**, **xdr5**, **agentix** | `/xsoar/public/v1` + suffix |
| **xsoar6** | Strip `/xsoar/public/v1`; legacy root path + suffix |

XSOAR 6 resolves e.g. `/settings/integration-commands` (not `/xsoar/public/v1/settings/integration-commands`). No separate legacy probe was needed — `xsoar_shaped_path()` already maps to the legacy path.

## Results

| profile | platform | endpoint | status code | notes |
| --- | --- | --- | --- | --- |
| xsoar-japac-dev | xsoar8 | GET /xsoar/public/v1/settings/integration-commands | 200 | success; response_size=17473136; items=376 |
| xsoar-japac-dev | xsoar8 | POST /xsoar/public/v1/settings/integration/search | 200 | success; response_size=45746169; keys=['instances', 'configurations', 'engines', 'health'] |
| xsoar-japac-dev | xsoar8 | POST /xsoar/public/v1/settings/credentials | 200 | success; response_size=2907; keys=['credentials', 'total']; total=8 |
| xsoar-japac-dev | xsoar8 | GET /xsoar/public/v1/contentpacks/metadata/installed | 200 | success; response_size=56524; items=257 |
| personal-xsoar6 | xsoar6 | GET /settings/integration-commands | 200 | success; response_size=1437781; items=59 |
| personal-xsoar6 | xsoar6 | POST /settings/integration/search | 200 | success; response_size=4374271; keys=['instances', 'configurations', 'engines', 'health'] |
| personal-xsoar6 | xsoar6 | POST /settings/credentials | 200 | success; response_size=28; keys=['credentials', 'total']; total=0 |
| personal-xsoar6 | xsoar6 | GET /contentpacks/metadata/installed | 200 | success; response_size=7918; items=36 |
| psojapac-xsiam | xsiam | GET /xsoar/public/v1/settings/integration-commands | 200 | success; response_size=26070830; items=608 |
| psojapac-xsiam | xsiam | POST /xsoar/public/v1/settings/integration/search | 200 | success; response_size=66195839; keys=['instances', 'configurations', 'engines', 'health'] |
| psojapac-xsiam | xsiam | POST /xsoar/public/v1/settings/credentials | 200 | success; response_size=3971; keys=['credentials', 'total']; total=21 |
| psojapac-xsiam | xsiam | GET /xsoar/public/v1/contentpacks/metadata/installed | 200 | success; response_size=98008; items=446 |
| cortex-cs-xdr5 | xdr5 | GET /xsoar/public/v1/settings/integration-commands | 200 | success; response_size=7632082; items=115 |
| cortex-cs-xdr5 | xdr5 | POST /xsoar/public/v1/settings/integration/search | 200 | success; response_size=14429256; keys=['instances', 'configurations', 'engines', 'health'] |
| cortex-cs-xdr5 | xdr5 | POST /xsoar/public/v1/settings/credentials | 200 | success; response_size=675; keys=['credentials', 'total']; total=2 |
| cortex-cs-xdr5 | xdr5 | GET /xsoar/public/v1/contentpacks/metadata/installed | 200 | success; response_size=17779; items=81 |
| cortex-cs-agentix | agentix | GET /xsoar/public/v1/settings/integration-commands | 200 | success; response_size=4687017; items=94 |
| cortex-cs-agentix | agentix | POST /xsoar/public/v1/settings/integration/search | 200 | success; response_size=9409510; keys=['instances', 'configurations', 'engines', 'health'] |
| cortex-cs-agentix | agentix | POST /xsoar/public/v1/settings/credentials | 200 | success; response_size=28; keys=['credentials', 'total']; total=0 |
| cortex-cs-agentix | agentix | GET /xsoar/public/v1/contentpacks/metadata/installed | 200 | success; response_size=14409; items=66 |

## Integration definition delete (lab-verified behaviour)

The XSOAR web UI deletes an entire integration **definition** (not just an instance) with
`POST …/settings/integration-conf/delete` and the **full ModuleConfiguration JSON** from
`integration/search` → `configurations[]` (including `integrationScript`, `configuration`, etc.).

| Platform | Path |
| --- | --- |
| **xsoar6** | `POST /settings/integration-conf/delete` |
| **xsoar8** (and cloud web-app routes) | `POST /xsoar/settings/integration-conf/delete` |

Do **not** use `DELETE …/settings/integration/{instance_id}` for definition removal — that
targets an integration **instance** only.

Toolkit helper: `cortex_ps_toolkit.integrations.api.delete_integration_configuration()`.

## Integration definition upload (lab-verified behaviour)

Custom integration definitions are uploaded with `POST …/settings/integration-conf/upload`
(multipart field `file`, demisto-style YAML).

| Platform | Path |
| --- | --- |
| **xsoar6** | `POST /settings/integration-conf/upload` |
| **xsoar8** (web-app) | `POST /xsoar/settings/integration-conf/upload` |

Toolkit helper: `cortex_ps_toolkit.integrations.api.upload_integration_yaml()`.

**Automated round-trip:** `tests/integration/test_integrations_live.py` uploads a temporary
`CptkUploadProbe` integration on all configured lab profiles (`LAB_TENANT_SLUGS`), verifies
read/search/upload/delete, then removes the probe.

## Copy / delete round-trip probe (2026-09-21)

Script: `scripts/probe_integrations_copy_delete.py`

```bash
cd /Users/weichen/Downloads/dev/cortex-ps-toolkit
PYTHONPATH=. python3 scripts/probe_integrations_copy_delete.py --output /tmp/integrations-probe.json
```

For each profile: read `integration-commands` + `integration/search`, upload `CptkUploadProbe.yml`,
verify in search, delete via `integration-conf/delete`.

| profile | platform | read | upload | verify | delete |
| --- | --- | --- | --- | --- | --- |
| personal-xsoar6 | xsoar6 | ✓ | ✓ 200 | ✓ | ✓ 200 |
| xsoar-japac-dev | xsoar8 | ✓ | ✓ 200 | ✓ | ✓ 200 |
| psojapac-xsiam | xsiam | ✓ | ✓ 200 | ✓ | ✓ 200 |
| cortex-cs-xdr5 | xdr5 | ✓ | ✓ 200 | ✓ | ✓ 200 |
| cortex-cs-agentix | agentix | ✓ | ✓ 200 | ✓ | ✓ 200 |

All five lab platforms passed read, upload, verify, and delete. `integrations.copy` and
`integrations.delete` are **documented** on xsoar6, xsoar8, xsiam, xdr5, and agentix
(experimental on xdr3 only — no lab tenant).

## Summary

All **20 probes** (4 endpoints × 5 profiles) returned **HTTP 200**.

| Endpoint | xsoar8 | xsoar6 | xsiam | xdr5 | agentix |
| --- | --- | --- | --- | --- | --- |
| GET integration-commands | ✓ | ✓ (legacy path) | ✓ | ✓ | ✓ |
| POST integration/search `{}` | ✓ | ✓ | ✓ | ✓ | ✓ |
| POST credentials `{page:0,size:10}` | ✓ | ✓ | ✓ | ✓ | ✓ |
| GET contentpacks/metadata/installed | ✓ | ✓ | ✓ | ✓ | ✓ |

### Observations

- **integration/search** responses are large (4–66 MB); consider pagination or field filtering if caching.
- **integration-commands** also returns large payloads on cloud tenants (7–26 MB).
- **credentials** POST accepts `{"page":0,"size":10}` on all platforms; empty tenants return `total=0`.
- **contentpacks/metadata/installed** returns a JSON array on all platforms; item counts vary by tenant content.

## Reproduce

```bash
cd /Users/weichen/Downloads/dev/cortex-ps-toolkit
python3 -m cortex_ps_toolkit.cli  # or inline probe using TenantClient + xsoar_shaped_path
```

Probe uses `TenantClient.session.request()` directly (does not call `_raise_for_status`) so non-2xx status codes are recorded without aborting the run.
