# Lists API — XDR 5 (compat path)

**Status:** Experimental — compat path on lab tenant.

**Lab tenant:** `cortex-cs-xdr5` (`xdr5`)

**Base URL:** `https://{tenant-host}/xsoar/public/v1/lists`

Same request/response shapes as [XSOAR 8](xsoar8.md).

```http
GET /xsoar/public/v1/lists HTTP/1.1
Host: api-cortex-cs.xdr.us.paloaltonetworks.com
Authorization: {api_key}
x-xdr-auth-id: {api_key_id}
```

**Response `200`:** JSON array — 8 lists on lab tenant (2026-09-17).

Sample item: [`samples/xdr5-list-item.json`](samples/xdr5-list-item.json).

Save/delete smoke test succeeded on lab tenant.
