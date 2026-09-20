# Profile context UI

Shows the active profile and copy-target profile details (slug, tenant type, API URL) below the header and copy panels.

Integrated in the standard dev server:

```bash
./scripts/dev-server.sh
```

## Files

| File | Role |
| --- | --- |
| `web/static/index.html` | Context bar markup + script load order |
| `web/static/styles.css` | `.profile-context` styles |
| `web/static/profile-context.js` | Context bar rendering and event hooks |
| `web/static/app.js` | Calls update hooks on route/profile changes |

Legacy serve-time injection helpers (`profile_context_patch.py`, `serve_with_profile_context.py`) remain for reference but are not required for normal use.
