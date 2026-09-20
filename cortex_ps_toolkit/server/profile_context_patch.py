"""HTML/CSS injection for profile context bars (avoids editing locked static assets)."""

from __future__ import annotations

PROFILE_CONTEXT_SCRIPT = '<script src="/static/profile-context.js"></script>'

PROFILE_CONTEXT_STYLE = """
<style id="profile-context-style">
.topbar-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  width: 100%;
}
.profile-context {
  margin: 0 1.25rem 0.75rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  color: var(--muted);
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  line-height: 1.4;
}
.profile-context.hidden {
  display: none;
}
.profile-context strong {
  color: var(--text);
  font-weight: 600;
}
.profile-context-url {
  word-break: break-all;
}
.profile-context-target {
  margin: 0.75rem 0 0;
}
</style>
"""

ACTIVE_PROFILE_CONTEXT = (
    '<div id="active-profile-context" class="profile-context hidden" aria-live="polite"></div>'
)

TARGET_CONTEXTS = {
    "copy-target": "lists-copy-target-context",
    "playbooks-copy-target": "playbooks-copy-target-context",
    "scripts-copy-target": "scripts-copy-target-context",
}


def patch_index_html(html: str) -> str:
    """Inject profile context UI into index.html at serve time."""
    if "</head>" in html and 'id="profile-context-style"' not in html:
        html = html.replace("</head>", f"{PROFILE_CONTEXT_STYLE}</head>", 1)

    header = html.find("<header class=\"topbar\">")
    if header >= 0:
        close = html.find("</header>", header)
        if close > header:
            block = html[header:close]
            if "topbar-row" not in block:
                inner_start = block.find(">") + 1
                inner = block[inner_start:]
                wrapped = (
                    '<header class="topbar"><div class="topbar-row">'
                    + inner
                    + "</div></header>"
                )
                html = html[:header] + wrapped + html[close + len("</header>") :]

    if 'id="active-profile-context"' not in html:
        marker = "</header>"
        pos = html.find(marker)
        if pos >= 0:
            insert_at = pos + len(marker)
            html = html[:insert_at] + ACTIVE_PROFILE_CONTEXT + html[insert_at:]

    for select_id, context_id in TARGET_CONTEXTS.items():
        if f'id="{context_id}"' in html:
            continue
        needle = f'<select id="{select_id}"></select>'
        pos = html.find(needle)
        if pos < 0:
            continue
        copy_row_end = html.find("</div>", pos)
        if copy_row_end < 0:
            continue
        insert_at = copy_row_end + len("</div>")
        snippet = (
            f'<div id="{context_id}" class="profile-context profile-context-target hidden" '
            f'aria-live="polite"></div>'
        )
        html = html[:insert_at] + snippet + html[insert_at:]

    if PROFILE_CONTEXT_SCRIPT not in html:
        html = html.replace(
            '<script src="/static/app.js"></script>',
            f"{PROFILE_CONTEXT_SCRIPT}\n  <script src=\"/static/app.js\"></script>",
            1,
        )

    return html
