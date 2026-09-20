/** Active and target profile context bars (slug, tenant type, URL). */

const TARGET_PROFILE_CONTEXTS = [
  ["copy-target", "lists-copy-target-context"],
  ["playbooks-copy-target", "playbooks-copy-target-context"],
  ["scripts-copy-target", "scripts-copy-target-context"],
];

const PROFILE_PICKER_ROUTES_FALLBACK = new Set(["lists", "playbooks", "scripts", "xql"]);

const PROFILE_CONTEXT_STYLE = `
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
`;

function profileBySlug(slug) {
  if (!slug) return null;
  const list = window.cptkProfiles || [];
  return list.find((p) => p.slug === slug) || null;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderProfileContext(profile, roleLabel) {
  if (!profile) {
    return "";
  }
  const name = profile.slug;
  const type = profile.tenant_type || "unknown";
  const url = profile.url || "";
  return (
    `${roleLabel}: <strong>${escapeHtml(name)}</strong>` +
    ` · ${escapeHtml(type)}` +
    ` · <span class="profile-context-url">${escapeHtml(url)}</span>`
  );
}

function setProfileContextElement(element, profile, roleLabel) {
  if (!element) return;
  if (!profile) {
    element.classList.add("hidden");
    element.innerHTML = "";
    return;
  }
  element.classList.remove("hidden");
  element.innerHTML = renderProfileContext(profile, roleLabel);
}

function currentRoute() {
  if (typeof routeFromHash === "function") {
    return routeFromHash();
  }
  const hash = location.hash.replace(/^#\/?/, "") || "credentials";
  return hash;
}

function pickerRoutes() {
  if (typeof PROFILE_PICKER_ROUTES !== "undefined") {
    return PROFILE_PICKER_ROUTES;
  }
  return PROFILE_PICKER_ROUTES_FALLBACK;
}

async function refreshProfileCacheContext() {
  const bar = document.getElementById("active-profile-context");
  if (!bar || bar.classList.contains("hidden")) return;
  const active = document.getElementById("active-profile");
  const profile = profileBySlug(active?.value);
  if (!profile || typeof api !== "function") return;
  try {
    const status = await api(`/api/cache/status?profile=${encodeURIComponent(profile.slug)}`);
    const cacheLine =
      typeof formatCacheStatusSummary === "function" ? formatCacheStatusSummary(status) : "";
    if (cacheLine) {
      bar.innerHTML = `${renderProfileContext(profile, "Operating on")}<br><span class="profile-context-cache">${cacheLine}</span>`;
    }
  } catch (_) {
    /* keep base profile line only */
  }
}

function updateActiveProfileContext() {
  const bar = document.getElementById("active-profile-context");
  if (!bar) return;
  const route = currentRoute();
  if (!pickerRoutes().has(route)) {
    bar.classList.add("hidden");
    bar.innerHTML = "";
    return;
  }
  const active = document.getElementById("active-profile");
  setProfileContextElement(bar, profileBySlug(active?.value), "Operating on");
  refreshProfileCacheContext();
}

window.refreshProfileCacheContext = refreshProfileCacheContext;

function updateTargetProfileContext(selectId, contextId) {
  const select = document.getElementById(selectId);
  setProfileContextElement(
    document.getElementById(contextId),
    profileBySlug(select?.value),
    "Copy target",
  );
}

function updateAllTargetProfileContexts() {
  TARGET_PROFILE_CONTEXTS.forEach(([selectId, contextId]) => {
    updateTargetProfileContext(selectId, contextId);
  });
}

function installProfileContextStyles() {
  if (document.getElementById("profile-context-style")) return;
  const style = document.createElement("style");
  style.id = "profile-context-style";
  style.textContent = PROFILE_CONTEXT_STYLE;
  document.head.appendChild(style);
}

function ensureActiveProfileContextBar() {
  if (document.getElementById("active-profile-context")) return;
  const header = document.querySelector("header.topbar");
  if (!header) return;

  if (!header.querySelector(".topbar-row")) {
    const row = document.createElement("div");
    row.className = "topbar-row";
    while (header.firstChild) {
      row.appendChild(header.firstChild);
    }
    header.appendChild(row);
  }

  const bar = document.createElement("div");
  bar.id = "active-profile-context";
  bar.className = "profile-context hidden";
  bar.setAttribute("aria-live", "polite");
  header.insertAdjacentElement("afterend", bar);
}

function ensureTargetProfileContextBars() {
  TARGET_PROFILE_CONTEXTS.forEach(([selectId, contextId]) => {
    if (document.getElementById(contextId)) return;
    const select = document.getElementById(selectId);
    if (!select) return;
    const copyRow = select.closest(".copy-row");
    if (!copyRow) return;
    const bar = document.createElement("div");
    bar.id = contextId;
    bar.className = "profile-context profile-context-target hidden";
    bar.setAttribute("aria-live", "polite");
    copyRow.insertAdjacentElement("afterend", bar);
  });
}

function installProfileContextDom() {
  installProfileContextStyles();
  ensureActiveProfileContextBar();
  ensureTargetProfileContextBars();
}

function bindProfileContextEvents() {
  const active = document.getElementById("active-profile");
  if (active && !active.dataset.profileContextBound) {
    active.dataset.profileContextBound = "1";
    active.addEventListener("change", updateActiveProfileContext);
  }

  TARGET_PROFILE_CONTEXTS.forEach(([selectId, contextId]) => {
    const select = document.getElementById(selectId);
    if (!select || select.dataset.profileContextBound) return;
    select.dataset.profileContextBound = "1";
    select.addEventListener("change", () => updateTargetProfileContext(selectId, contextId));
  });

  if (!window.__profileContextHashBound) {
    window.__profileContextHashBound = true;
    window.addEventListener("hashchange", updateActiveProfileContext);
  }
}

function refreshProfileContextBars() {
  installProfileContextDom();
  bindProfileContextEvents();
  updateActiveProfileContext();
  updateAllTargetProfileContexts();
}

function watchProfileData() {
  let lastSignature = "";
  window.setInterval(() => {
    const active = document.getElementById("active-profile");
    const profilesLen = (window.cptkProfiles || []).length;
    const signature = `${profilesLen}:${active?.value || ""}:${currentRoute()}`;
    if (signature === lastSignature) return;
    lastSignature = signature;
    refreshProfileContextBars();
  }, 400);
}

function initProfileContext() {
  refreshProfileContextBars();
  watchProfileData();
}

window.profileBySlug = profileBySlug;
window.renderProfileContext = renderProfileContext;
window.updateActiveProfileContext = updateActiveProfileContext;
window.updateAllTargetProfileContexts = updateAllTargetProfileContexts;
window.bindProfileContextEvents = bindProfileContextEvents;

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initProfileContext);
} else {
  initProfileContext();
}
