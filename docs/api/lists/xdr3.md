# Lists API — XDR 3 (compat path)

**Status:** Assumed same as [XDR 5](xdr5.md) — no dedicated XDR 3 lab tenant registered yet.

**Expected base URL:** `https://{tenant-host}/xsoar/public/v1/lists`

Use the same auth headers, paths, and payloads documented for XDR 5. When an `xdr3` profile is added to `presets/credentials/lab-sources.json`, run:

```bash
python -m cortex_ps_toolkit lists refresh --profile <xdr3-slug>
```

Then add a row to [`README.md`](README.md) and a sample under [`samples/`](samples/).
