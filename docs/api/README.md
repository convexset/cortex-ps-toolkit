# API documentation

Reference for **tenant-facing Cortex APIs** used by the toolkit and **local toolkit REST APIs** exposed by the dev server.

| Section | Contents |
| --- | --- |
| [Lists API overview](lists/README.md) | Auth, path rules, operation index |
| [Lists — XSOAR 6](lists/xsoar6.md) | Legacy `/lists` paths (lab-verified) |
| [Lists — XSOAR 8](lists/xsoar8.md) | Documented `/xsoar/public/v1/lists` |
| [Lists — XSIAM](lists/xsiam.md) | Compat path (experimental) |
| [Lists — XDR 5](lists/xdr5.md) | Compat path (experimental) |
| [Lists — XDR 3](lists/xdr3.md) | Same as XDR 5 (assumed) |
| [Lists — AgentiX](lists/agentix.md) | Compat path (experimental) |
| [Toolkit REST — Credentials](toolkit/credentials.md) | `/api/credentials` |
| [Toolkit REST — Lists](toolkit/lists.md) | `/api/lists` |
| [Toolkit REST — Playbooks](toolkit/playbooks.md) | `/api/playbooks` |
| [Toolkit REST — Scripts](toolkit/scripts.md) | `/api/scripts` |
| [Toolkit REST — Integrations](toolkit/integrations.md) | `/api/integrations/*` |
| [Toolkit REST — Vault](toolkit/vault.md) | `/api/vault/*` (local encrypted store) |
| [Toolkit REST — XQL](toolkit/xql.md) | `/api/xql/*` |
| [**Toolkit web API — master table**](toolkit/WEB-API.md) | All REST routes, CLI, UI, tenant paths, platform support |
| [Content CLI reference](../CONTENT-CLI.md) | Lists, playbooks, scripts, cache, serve, XQL |
| [List Tools agent guide](../LISTS-AGENTS.md) | Lists CLI, modules, lab tenants |
| [Design-time content probe](../api-compat/content-probe.md) | Incident fields/types, layouts, bundle, VC — CRUD paths by platform |
| [System management / RBAC probe](../api-compat/system-management-probe.md) | Get users, roles, user groups; set user role (xsoar8, xsiam, xdr5, agentix) |
| [API Keys probe](../api-compat/api-keys-probe.md) | Get, generate, delete API keys (xsoar8, xsiam, xdr5, agentix) |
| [Integrations probe](../api-compat/integrations-probe.md) | Settings, credentials, content packs |

Sample payloads captured from lab tenants (2026-09-17) live under [`lists/samples/`](lists/samples/).

Official XSOAR 8 Lists reference: [cortex-docs — Lists](https://cortex-docs.paloaltonetworks.com/xsoar-8-api/cortex-xsoar-8.x-apis/lists).
