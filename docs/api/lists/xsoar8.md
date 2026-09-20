# Lists API — XSOAR 8

**Documented:** [Lists — Cortex XSOAR 8 API](https://cortex-docs.paloaltonetworks.com/xsoar-8-api/cortex-xsoar-8.x-apis/lists)

**Lab tenant:** `xsoar-japac-dev` (`xsoar8`)

**Base URL:** `https://{tenant-host}/xsoar/public/v1/lists`

## GET all lists

```http
GET /xsoar/public/v1/lists HTTP/1.1
Host: api-xsoar-japac-test.crtx.au.paloaltonetworks.com
Authorization: {api_key}
x-xdr-auth-id: {api_key_id}
```

**Response `200`:** JSON array of list objects.

```json
[
  {
    "id": "Analyst Tool",
    "version": 2,
    "name": "Analyst Tool",
    "type": "plain_text",
    "data": "| [malware](https://example/) | Check a information on google!",
    "description": "",
    "allRead": true,
    "allReadWrite": true,
    "modified": "2023-08-07T02:59:50.351188626Z",
    "truncated": false
  }
]
```

Full lab sample item: [`samples/xsoar8-list-item.json`](samples/xsoar8-list-item.json).

## POST save (create)

```http
POST /xsoar/public/v1/lists/save HTTP/1.1
Content-Type: application/json

{
  "name": "_CPTK_TOOLKIT_TEST",
  "data": "line1",
  "type": "plain_text",
  "description": "toolkit smoke test",
  "allRead": true,
  "allReadWrite": true,
  "shouldCommit": false,
  "shouldPublish": false
}
```

**Response `200`:** Saved list object (includes `id`, `version`).

## POST save (update)

Include `id` and current `version` from a prior GET, plus updated fields.

## POST delete

```http
POST /xsoar/public/v1/lists/delete HTTP/1.1
Content-Type: application/json

{ "id": "_CPTK_TOOLKIT_TEST" }
```

**Response `200`:** `{}` (empty object observed on lab tenant).

## GET download

```http
GET /xsoar/public/v1/lists/download/{list_id} HTTP/1.1
```

**Response `200`:** JSON array of strings (lines) when list body is line-oriented.
