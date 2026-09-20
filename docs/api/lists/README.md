# Lists API — overview

XSOAR **Lists** endpoints used by `cortex_ps_toolkit lists` and **List Tools** in the web UI.

## Path resolution

| Platform | Base path | Status |
| --- | --- | --- |
| xsoar8 | `/xsoar/public/v1/lists` | Documented |
| xsoar6 | `/lists` | Lab-verified (strip cloud prefix) |
| xsiam, xdr3, xdr5, agentix | `/xsoar/public/v1/lists` | Compat (lab-verified except xdr3) |

See also [`../../PLATFORMS.md`](../../PLATFORMS.md) § Compatibility API paths.

## Authentication

| Platform | Headers |
| --- | --- |
| xsoar6 | `Authorization: {api_key}` |
| xsoar8, xsiam, xdr5, agentix | `Authorization: {api_key}` + `x-xdr-auth-id: {api_key_id}` |

Optional: disable TLS verification per credential profile (`verify_ssl: false`).

## Operations

| Operation | Method | Path suffix | Platform docs |
| --- | --- | --- | --- |
| Get all lists | `GET` | `` or `/` | [xsoar8](xsoar8.md), [xsoar6](xsoar6.md), … |
| Download list | `GET` | `/download/{list_id}` | All |
| Save (create/update) | `POST` | `/save` | All |
| Delete | `POST` | `/delete` | All |

## Lab tenants used for samples (2026-09-17)

| Platform | Profile slug | Sample file |
| --- | --- | --- |
| xsoar6 | `personal-xsoar6` | [`samples/xsoar6-list-item.json`](samples/xsoar6-list-item.json) |
| xsoar8 | `xsoar-japac-dev` | [`samples/xsoar8-list-item.json`](samples/xsoar8-list-item.json) |
| xsiam | `psojapac-xsiam` | [`samples/xsiam-list-item.json`](samples/xsiam-list-item.json) |
| xdr5 | `cortex-cs-xdr5` | [`samples/xdr5-list-item.json`](samples/xdr5-list-item.json) |
| agentix | `cortex-cs-agentix` | [`samples/agentix-list-item.json`](samples/agentix-list-item.json) |

## Toolkit wrapper

Local REST: [`../toolkit/lists.md`](../toolkit/lists.md).
