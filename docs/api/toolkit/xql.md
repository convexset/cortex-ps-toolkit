# Toolkit REST — XQL

## POST /api/xql/run

**Request:**

```json
{
  "profile": "psojapac-xsiam",
  "query": "dataset = xdr_data | limit 5",
  "timeframe": { "relativeTime": 86400000 }
}
```

**Response:** rows, columns, metrics, query id (when stored).

**CLI:**

```bash
python3 -m cortex_ps_toolkit xql run --profile psojapac-xsiam \
  --query "dataset = xdr_data | limit 5" --timeframe-hours 24
```

**Tenant APIs:**

| Step | Path |
| --- | --- |
| Start | `POST {host}/public_api/v1/xql/start_xql_query` |
| Poll | `POST {host}/public_api/v1/xql/get_query_results` |
| Stream | `POST {host}/public_api/v1/xql/get_query_results_stream` |

**Operation:** `xql.run` — **not** available on XSOAR 6/8.

## Presets

| Route | Method | UI |
| --- | --- | --- |
| `/api/xql/presets/builtin` | GET | Built-in preset dropdown |
| `/api/xql/presets/user` | GET/POST | Saved user presets |
| `/api/xql/presets/user/{preset_id}` | DELETE | Remove preset |

**CLI:** Presets are web-only; query text via `--query` / `--query-file`.

## Custom visualisations

See [`../../xql-visual-builder.md`](../../xql-visual-builder.md).

| Route | Method |
| --- | --- |
| `/api/xql/visualizations/chart-types` | GET |
| `/api/xql/visualizations/schema` | POST |
| `/api/xql/visualizations/validate` | POST |
| `/api/xql/visualizations/render` | POST |
| `/api/xql/visualizations` | GET / POST |
| `/api/xql/visualizations/{visualization_id}` | DELETE |

Master table: [`WEB-API.md`](WEB-API.md)
