# Platform support

Cortex PS Toolkit targets six Cortex platform families. Each feature records **which platforms it supports** and whether support is **documented** or **experimental** (known to work but not guaranteed in official docs).

Official API overviews:

| Platform | Toolkit id | API documentation |
| --- | --- | --- |
| Cortex XSOAR 6 | `xsoar6` | [XSOAR 6 APIs Overview](https://cortex-docs.paloaltonetworks.com/xsoar-6-api/cortex-xsoar-6.x-apis/cortex-xsoar-6-apis-overview) |
| Cortex XSOAR 8 | `xsoar8` | [XSOAR 8 APIs Overview](https://cortex-docs.paloaltonetworks.com/xsoar-8-api/cortex-xsoar-8.x-apis/cortex-xsoar-8-apis-overview) |
| Cortex XSIAM | `xsiam` | [Get started with Cortex XSIAM APIs](https://cortex-docs.paloaltonetworks.com/xsiam-api) |
| Cortex XDR 3.x | `xdr3` | [Get started with Cortex XDR 3.x APIs](https://cortex-docs.paloaltonetworks.com/xdr-3-api) |
| Cortex XDR 5.x | `xdr5` | [Get started with Cortex XDR 5.x APIs](https://cortex-docs.paloaltonetworks.com/xdr-5-api) |
| Cortex AgentiX | `agentix` | [Get started with Cortex AgentiX APIs](https://cortex-docs.paloaltonetworks.com/agentix-api) |

Markdown API pages: append `.md` to doc URLs (see [llms.txt](https://cortex-docs.paloaltonetworks.com/llms.txt)).

---

## Support levels

| Level | Meaning |
| --- | --- |
| **documented** | Described in the platform's official API docs; toolkit implements against documented paths |
| **experimental** | Observed working on a lab tenant or via cross-platform path substitution — **not** guaranteed |
| **unsupported** | Operation blocked; CLI/API returns a clear error |

Code registry: `cortex_ps_toolkit/platforms.py` → `OPERATIONS`. Path rules: `cortex_ps_toolkit/core/paths.py` (`xsoar_shaped_path`, `xsoar_webapp_path`, content URL helpers). Design-time content CRUD matrix: [api-compat/content-probe.md](api-compat/content-probe.md). CLI:

```bash
cd /Users/weichen/Downloads/dev/cortex-ps-toolkit
python -m cortex_ps_toolkit platforms list
python -m cortex_ps_toolkit platforms list --docs
python -m cortex_ps_toolkit platforms show content.lists.manage
```

Before implementing a feature, add or update its `OperationSpec`. At runtime, call `assert_operation_supported(operation_id, profile.tenant_type)`.

---

## Compatibility API paths

Many **content** APIs (playbooks, lists, automations) are documented for **XSOAR 8** under:

```text
/xsoar/public/v1/{resource}/...
```

Lab tenants on **XSIAM, XDR, and AgentiX** often expose the **same XSOAR-shaped paths** at that prefix even when the platform's primary docs emphasise different bases (`/public_api/v1`, `/XDR/public/v1`, `/agentix/public/v1`, etc.).

### Path substitution rules

When porting an endpoint from [XSOAR 8 API docs](https://cortex-docs.paloaltonetworks.com/xsoar-8-api/cortex-xsoar-8.x-apis/cortex-xsoar-8-apis-overview):

| Platform | Rule | Example (Lists GET) |
| --- | --- | --- |
| **xsoar8** | Use documented path as-is | `/xsoar/public/v1/lists` |
| **xsoar6** | **Remove** `/xsoar/public/v1` prefix | `/lists` |
| **xsiam**, **xdr3**, **xdr5**, **agentix** | **Keep** `/xsoar/public/v1` prefix (compat) | `/xsoar/public/v1/lists` |

**Working assumption:** `xdr3` behaves like `xdr5` for compat paths until a lab tenant shows otherwise. Both are in `XSOAR_COMPAT_PLATFORMS` in `core/paths.py`.

Implementation helper:

```python
from cortex_ps_toolkit.core.paths import xsoar_shaped_path, xsoar_shaped_url

# XSOAR 8 doc says GET /xsoar/public/v1/lists
path = xsoar_shaped_path(profile.tenant_type, "/lists")
url = xsoar_shaped_url(profile.host, profile.tenant_type, "/lists/save")
```

### Verified compat endpoints (lab)

Last live run: **2026-09-17** via `python -m cortex_ps_toolkit {playbooks,scripts} refresh --profile …`.

| Capability | Endpoint (compat where noted) | xsoar6 | xsoar8 | xsiam | xdr5 | agentix | xdr3 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Lists refresh + CRUD | `/lists` or `/xsoar/public/v1/lists` | ✓ | ✓ | ✓ | ✓ | ✓ | *assumed* |
| **Scripts cache refresh** | `POST /xsoar/public/v1/automation/search` | ✓ legacy | ✓ | ✓ compat | ✓ compat | ✓ compat | *assumed* |
| **Playbooks cache refresh** | `POST /xsoar/public/v1/playbook/search` | ✓ legacy | ✓ | ✓ compat | ✓ compat | ✓ compat | *assumed* |

**Lab counts (2026-09-17):** all refreshes returned HTTP 200 unless noted.

| Profile | Platform | Scripts | Playbooks |
| --- | --- | ---: | ---: |
| `personal-xsoar6` | xsoar6 | 495 | 213 |
| `xsoar-japac-dev` | xsoar8 | 981 | 995 |
| `psojapac-xsiam` | xsiam | 1336 | 2280 |
| `bay-xsiam-1` | xsiam | 648 | 603 |
| `bay-xsiam-2` | xsiam | 648 | 603 |
| `mfec-uat` | xsiam | 544 | 337 |
| `cortex-cs-xdr5` | xdr5 | 588 | 423 |
| `cortex-cs-agentix` | agentix | 552 | 352 |

**Notes:**

- Scripts and playbooks on **XSIAM / XDR5 / AgentiX** use `POST /xsoar/public/v1/automation/search` and `POST /xsoar/public/v1/playbook/search` (compat; `compat_mode: true` on scripts).
- **XSOAR 6 / 8** use the same shaped paths (`/playbook/search`, `/automation/search` under `/xsoar/public/v1` for 8; legacy root paths for 6).
- Playbook search initially failed with HTTP 415 on all tenants because an empty `{}` body was sent without `Content-Type: application/json` (`payload or None` treated `{}` as falsy). Fixed in `playbooks/api.py`.
- XSIAM playbook search can take **30–90s** on large tenants (extended timeout to 300s on compat platforms).

Record new rows here after live verification. Include tenant slug and date in commit notes.

### Integrations, tenant credentials, installed packs (2026-09-18)

Full probe report: [`docs/api-compat/integrations-probe.md`](api-compat/integrations-probe.md).

| Endpoint | xsoar6 | xsoar8 | xsiam | xdr5 | agentix |
| --- | --- | --- | --- | --- | --- |
| `GET …/settings/integration-commands` | ✓ legacy | ✓ | ✓ compat | ✓ compat | ✓ compat |
| `POST …/settings/integration/search` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `POST …/settings/credentials` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `GET …/contentpacks/metadata/installed` | ✓ | ✓ | ✓ | ✓ | ✓ |

**Lab profiles probed:** `xsoar-japac-dev`, `personal-xsoar6`, `psojapac-xsiam`, `cortex-cs-xdr5`, `cortex-cs-agentix` — **20/20 HTTP 200**.

**Notes:**

- `integration/search` and `integration-commands` responses are **very large** on cloud tenants (up to ~66 MB / ~26 MB). First cache refresh may take minutes; payloads are sanitized and indexed before UI display.
- Tenant credentials list returns **metadata only** (`hasPassword`, `user`, `name`, …) — no secret values.

Toolkit refresh: Integrations panel → **Refresh cache**, or `POST /api/integrations/refresh`.

---

## How to experiment across platforms

Use this workflow when adding or extending a feature:

1. **Start from XSOAR 8 docs** — find the official path (e.g. [Lists API](https://cortex-docs.paloaltonetworks.com/xsoar-8-api/cortex-xsoar-8.x-apis/lists)).
2. **Register the operation** in `platforms.py`:
   - `documented` for xsoar6/xsoar8 only when paths are confirmed
   - `experimental` for xsiam, xdr3, xdr5, agentix when using compat prefix
3. **Route paths** via `xsoar_shaped_path()` in `core/paths.py` — do not hardcode per feature.
4. **Gate at runtime** with `assert_operation_supported()` so unsupported combos fail clearly.
5. **Test on lab tenants** — import credentials, run CLI against each platform family:

```bash
python -m cortex_ps_toolkit credentials import-lab
python -m cortex_ps_toolkit lists refresh --profile xsoar-japac-dev      # xsoar8
python -m cortex_ps_toolkit lists refresh --profile personal-xsoar6      # xsoar6
python -m cortex_ps_toolkit lists refresh --profile psojapac-xsiam       # xsiam
python -m cortex_ps_toolkit lists refresh --profile cortex-cs-xdr5       # xdr5
python -m cortex_ps_toolkit lists refresh --profile cortex-cs-agentix    # agentix
# xdr3: use xdr5 paths until an xdr3 lab tenant is available
```

6. **Promote support level** — after repeated success on a platform, move from `experimental` → `documented` in `OPERATIONS` and update the verified table above.

**Smoke-test pattern for mutating APIs:** create a uniquely named object (e.g. `_CPTK_TOOLKIT_TEST`), verify save response, delete, confirm cache refresh.

---

## Authentication patterns

| Platform family | Auth headers | Notes |
| --- | --- | --- |
| XSOAR 6 | `Authorization: {key}` | Often no API key id; `verify_ssl: false` for self-signed lab hosts |
| XSOAR 8 | `Authorization: {key}` + `x-xdr-auth-id` | Public API under `/xsoar/public/v1/` |
| XSIAM / XDR / AgentiX | `Authorization: {key}` + `x-xdr-auth-id: {key_id}` | Compat content APIs still use `/xsoar/public/v1/...`; native APIs use platform prefix |

Advanced API keys (nonce + timestamp hash) are documented for [XDR](https://cortex-docs.paloaltonetworks.com/xdr-3-api) tenants — support as a follow-up in `core/client.py`.

---

## Lab credential profiles

Imported from `bay/*.json` via `credentials import-lab`. Stored in gitignored `data/collections/credentials.json`.

| Slug | Platform | Source file | Notes |
| --- | --- | --- | --- |
| `xsoar-japac-dev` | `xsoar8` | `bay/lab-xsoar-credentials.json` | JAPAC test XSOAR 8 |
| `personal-xsoar6` | `xsoar6` | `bay/personal-xsoar6-credentials.json` | Self-signed TLS (`verify_ssl: false`) |
| `bay-xsiam-1` | `xsiam` | `bay/bay-credentials.json` | Expires end Nov 2026 |
| `bay-xsiam-2` | `xsiam` | `bay/bay-credentials-2.json` | Expires end Nov 2026 |
| `mfec-uat` | `xsiam` | `bay/mfec-uat-credentials.json` | Expires end Nov 2026 |
| `psojapac-xsiam` | `xsiam` | `bay/lab-xsiam-credentials.json` | PSO JAPAC lab |
| `cortex-cs-xdr5` | `xdr5` | `bay/lab-xdr-credentials.json` | Lists compat verified 2026-09 |
| `cortex-cs-agentix` | `agentix` | `bay/lab-agentix-credentials.json` | Lists compat verified 2026-09 |

**No lab tenant today:** XDR 3 — treat as xdr5 for path purposes until tested.

Import:

```bash
python -m cortex_ps_toolkit credentials import-lab
python -m cortex_ps_toolkit credentials list
```

Manifest (paths only, no secrets): [`presets/credentials/lab-sources.json`](../presets/credentials/lab-sources.json).

---

## Operation matrix (summary)

| Operation | xsoar6 | xsoar8 | xsiam | xdr3 | xdr5 | agentix |
| --- | --- | --- | --- | --- | --- | --- |
| credentials.validate | doc | doc | doc | doc | doc | doc |
| content.lists.manage | doc | doc | exp | exp | exp | exp |
| cache.playbooks.refresh | doc | doc | doc | - | exp | exp |
| cache.scripts.refresh | doc | doc | doc | - | exp | exp |
| cache.integrations.* | doc | doc | doc | - | doc | doc |
| cache.credentials.refresh | doc | doc | doc | - | doc | doc |
| cache.contentpacks.refresh | doc | doc | doc | - | doc | doc |
| playbooks.* | doc | doc | doc | - | - | - |
| xql.run | - | - | doc | doc | doc | exp |
| content.correlation_rules | - | - | doc | - | exp | exp |
| content.widgets | doc | doc | exp | - | - | - |

Run `platforms list` for the live registry (source of truth).

---

## API path prefixes (implementation reference)

| Platform | Documented base | XSOAR-shaped compat base |
| --- | --- | --- |
| XSOAR 6 | `/` (legacy) | — (strip `/xsoar/public/v1` from XSOAR 8 paths) |
| XSOAR 8 | `/xsoar/public/v1/...` | same |
| XSIAM | `/public_api/v1/...` | `/xsoar/public/v1/...` |
| XDR 3 / 5 | `/public_api/v1/...` or `/XDR/public/v1/...` | `/xsoar/public/v1/...` (xdr3 ≈ xdr5) |
| AgentiX | `/agentix/public/v1/...` | `/xsoar/public/v1/...` |

Routing lives in `core/client.py` and `core/paths.py`.

---

## Updating this document

When you verify an operation on a lab tenant:

1. Update `OPERATIONS` in `platforms.py` (`documented` vs `experimental`)
2. Add a row to **Verified compat endpoints**
3. Update the lab profiles table if a new tenant was added
4. Note the working path and date in commit message or PR description
