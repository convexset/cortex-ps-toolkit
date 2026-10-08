# XQL custom visual builder

User-defined charts for XQL result sets in the **XQL Query Tool** (`web/static/xql-monitor.html`).

## Principles

- **XQL aggregates** — each row is a bar segment, scatter point, or gantt task. The toolkit does not `sum()` or group in the chart layer.
- **Long/tidy data** for stacked bars: `category`, optional `stack`, `measure` columns (see examples in planning notes).
- **Validation** rejects duplicate categories when Stack is unset, and duplicate `(category, stack)` pairs when Stack is set.

## Chart types (v1)

| ID | Label |
| --- | --- |
| `stacked_bar_horizontal` | Horizontal stacked bar |
| `stacked_bar_vertical` | Vertical stacked bar |
| `scatter` | Scatter (numeric or time X, numeric Y) |
| `gantt` | Gantt (label, start, end or duration) |

Encodings are declared per chart type in `cortex_ps_toolkit/xql/visualizations/registry.py`.

## API (toolkit dev server)

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/xql/visualizations/chart-types` | GET | Slot metadata for UI |
| `/api/xql/visualizations/schema` | POST | `{ rows }` → inferred column types |
| `/api/xql/visualizations/validate` | POST | `{ rows, spec }` → errors/warnings |
| `/api/xql/visualizations/render` | POST | `{ rows, spec }` → Plotly `{ data, layout }` |
| `/api/xql/visualizations` | GET | List saved specs (`?profile=`) |
| `/api/xql/visualizations` | POST | Save spec to `data/collections/xql_visualizations.json` |
| `/api/xql/visualizations/{id}` | DELETE | Remove saved spec |

## UI flow

1. Run query or load TSV/JSONL.
2. Click **Custom chart…** under Results.
3. Choose chart type and map columns to encodings (optional slots = “not used”).
4. **Validate** or **Render chart**.
5. **Save visual** — localStorage plus server copy when embedded in the toolkit with a profile.

Preset **Quick charts** (schema auto-detect) remain unchanged.

### Case / Issue Duration — Time in System

The **Case Duration** preset chart set includes a step line (**Time in System**) built from row-level
`create_time` / `resolution_time` (+1/−1 events, running total). Logic is mirrored in
`cortex_ps_toolkit/xql/visualizations/time_in_system.py` (includes unresolved issues without a resolution event).

## Spec shape

```json
{
  "chart_type": "stacked_bar_horizontal",
  "label": "Incidents by type",
  "title": "SOC volume",
  "encodings": {
    "category": { "field": "incident_type", "type": "text" },
    "measure": { "field": "total_count", "type": "number" },
    "stack": { "field": "severity", "type": "text" },
    "color": null
  },
  "display": { "limit_categories": 20 }
}
```

Normalization uses `content/representation`-style rules in `xql/schema.py` for type inference only; refactor compare (`playbook-utils`) is **not** used here.

## Related

- [`docs/FEATURES.md`](FEATURES.md) § XQL visualisations
- [`docs/api/toolkit/xql.md`](api/toolkit/xql.md)
