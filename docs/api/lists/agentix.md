# Lists API — AgentiX (compat path)

**Status:** Experimental — compat path on lab tenant.

**Lab tenant:** `cortex-cs-agentix` (`agentix`)

**Base URL:** `https://{tenant-host}/xsoar/public/v1/lists`

Same request/response shapes as [XSOAR 8](xsoar8.md).

```http
GET /xsoar/public/v1/lists HTTP/1.1
Host: api-csagentix.xdr.us.paloaltonetworks.com
Authorization: {api_key}
x-xdr-auth-id: {api_key_id}
```

**Response `200`:** JSON array — 11 lists on lab tenant (2026-09-17).

Sample item: [`samples/agentix-list-item.json`](samples/agentix-list-item.json).

Save/delete smoke test succeeded on lab tenant.
