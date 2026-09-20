# Lists API — XSOAR 6

**Status:** Speculative — same operations as XSOAR 8 with `/xsoar/public/v1` prefix removed.

**Lab tenant:** `personal-xsoar6` (`xsoar6`, `verify_ssl: false`)

**Base URL:** `https://{tenant-host}/lists`

Derived from XSOAR 8 paths via `xsoar_shaped_path()` in `core/paths.py`.

## GET all lists

```http
GET /lists HTTP/1.1
Host: xsoar6.random-samplings.org
Authorization: {api_key}
```

No `x-xdr-auth-id` required on this lab tenant (`api_id` null).

**Response `200`:** JSON array (same object shape as XSOAR 8; may omit `sequenceNumber` / `primaryTerm`).

Sample item: [`samples/xsoar6-list-item.json`](samples/xsoar6-list-item.json).

## POST save / POST delete / GET download

| XSOAR 8 path | XSOAR 6 path |
| --- | --- |
| `/xsoar/public/v1/lists/save` | `/lists/save` |
| `/xsoar/public/v1/lists/delete` | `/lists/delete` |
| `/xsoar/public/v1/lists/download/{id}` | `/lists/download/{id}` |

Request and response bodies match XSOAR 8. Lab-verified: create + delete `_CPTK_TOOLKIT_TEST` on `personal-xsoar6`.
