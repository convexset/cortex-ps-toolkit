# Lists API — XSIAM (compat path)

**Status:** Experimental — not emphasized in XSIAM product docs; works via XSOAR-shaped compat path on lab tenant.

**Lab tenant:** `psojapac-xsiam` (`xsiam`)

**Base URL:** `https://{tenant-host}/xsoar/public/v1/lists`

Same paths and payloads as [XSOAR 8](xsoar8.md).

```http
GET /xsoar/public/v1/lists HTTP/1.1
Host: api-psojapac-xsiam.xdr.au.paloaltonetworks.com
Authorization: {api_key}
x-xdr-auth-id: {api_key_id}
```

**Response `200`:** JSON array — 150 lists observed on lab refresh (2026-09-17).

Sample item: [`samples/xsiam-list-item.json`](samples/xsiam-list-item.json).

Save/delete smoke test: `_CPTK_TOOLKIT_TEST` create + delete succeeded on lab tenant.
