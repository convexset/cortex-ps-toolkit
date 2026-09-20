/** Shared profile capability helpers for tab and rail visibility. */

const CPTK_VIEW_SECTIONS = {
  object_setup: [
    "incident-types",
    "incident-fields",
    "layouts",
    "classifiers",
    "preprocess",
    "correlation-rules",
  ],
  indicators: ["indicators", "biocs"],
  system_admin: ["rbac-users", "rbac-roles", "rbac-groups", "api-keys"],
};

const CPTK_CAPABILITY_ROUTES = {
  "object-setup": "object_setup",
  "design-content": "object_setup",
  indicators: "indicators",
  "platform-admin": "indicators",
  "system-admin": "system_admin",
};

const CPTK_VIEW_LABELS = {
  object_setup: "Object Setup",
  indicators: "Indicators",
  system_admin: "User Administration",
};

let _cachedCapabilities = null;
let _cachedCapabilitiesProfile = null;

function cptkNormalizeRoute(route) {
  if (route === "design-content") return "object-setup";
  if (route === "platform-admin") return "indicators";
  return route;
}

function cptkIsSectionSupported(caps, groupKey, sectionId) {
  if (!caps) return true;
  const entry = caps[groupKey]?.[sectionId];
  if (!entry) return false;
  return Boolean(entry.list) || entry.support !== "unsupported";
}

function cptkSupportedSections(caps, groupKey, sectionIds) {
  if (!caps) return [...sectionIds];
  return sectionIds.filter((id) => cptkIsSectionSupported(caps, groupKey, id));
}

function cptkViewHasAnySupport(caps, route) {
  const normalized = cptkNormalizeRoute(route);
  const groupKey = CPTK_CAPABILITY_ROUTES[normalized] || CPTK_CAPABILITY_ROUTES[route];
  if (!groupKey) return true;
  if (!caps) return true;
  return cptkSupportedSections(caps, groupKey, CPTK_VIEW_SECTIONS[groupKey]).length > 0;
}

function cptkNoSectionsMessage(groupKey) {
  const label = CPTK_VIEW_LABELS[groupKey] || groupKey;
  return `No ${label} features are available for this platform.`;
}

function cptkApplyTabCapabilities({
  caps,
  groupKey,
  sectionIds,
  activeId,
  storageKey,
  tabSelector,
  dataAttr,
  activeClass = "active",
}) {
  const supported = cptkSupportedSections(caps, groupKey, sectionIds);
  document.querySelectorAll(tabSelector).forEach((btn) => {
    const id = btn.dataset[dataAttr];
    btn.classList.toggle("hidden", caps ? !supported.includes(id) : false);
  });

  let nextActive = activeId;
  let changed = false;
  if (caps && supported.length && !supported.includes(activeId)) {
    nextActive = supported[0];
    changed = true;
    if (storageKey) localStorage.setItem(storageKey, nextActive);
  }

  document.querySelectorAll(tabSelector).forEach((btn) => {
    const id = btn.dataset[dataAttr];
    btn.classList.toggle(activeClass, id === nextActive);
  });

  return { active: nextActive, changed, supported };
}

function cptkUpdateCapabilityRails(caps) {
  document.querySelectorAll(".rail-btn").forEach((btn) => {
    const route = btn.dataset.route;
    if (!CPTK_CAPABILITY_ROUTES[route]) return;
    btn.classList.toggle("hidden", caps ? !cptkViewHasAnySupport(caps, route) : false);
  });
}

async function cptkFetchProfileCapabilities(profile) {
  if (!profile) return null;
  try {
    return await api(`/api/profile/capabilities?profile=${encodeURIComponent(profile)}`);
  } catch {
    return null;
  }
}

async function cptkRefreshProfileCapabilities(profile, { force = false } = {}) {
  if (!profile) {
    _cachedCapabilities = null;
    _cachedCapabilitiesProfile = null;
    cptkUpdateCapabilityRails(null);
    return null;
  }
  if (!force && profile === _cachedCapabilitiesProfile && _cachedCapabilities) {
    cptkUpdateCapabilityRails(_cachedCapabilities);
    return _cachedCapabilities;
  }
  const caps = await cptkFetchProfileCapabilities(profile);
  _cachedCapabilities = caps;
  _cachedCapabilitiesProfile = profile;
  cptkUpdateCapabilityRails(caps);
  return caps;
}

function cptkGetCachedProfileCapabilities() {
  return _cachedCapabilities;
}

function cptkFirstSupportedCapabilityRoute(caps) {
  const order = ["object-setup", "indicators", "system-admin"];
  for (const route of order) {
    if (cptkViewHasAnySupport(caps, route)) return route;
  }
  return null;
}

function cptkEnsureRouteSupported(caps, route) {
  const normalized = cptkNormalizeRoute(route);
  if (!CPTK_CAPABILITY_ROUTES[normalized]) return route;
  if (!caps) return route;
  if (cptkViewHasAnySupport(caps, normalized)) return route;
  return cptkFirstSupportedCapabilityRoute(caps) || "credentials";
}

window.cptkApplyTabCapabilities = cptkApplyTabCapabilities;
window.cptkRefreshProfileCapabilities = cptkRefreshProfileCapabilities;
window.cptkGetCachedProfileCapabilities = cptkGetCachedProfileCapabilities;
window.cptkEnsureRouteSupported = cptkEnsureRouteSupported;
window.cptkNoSectionsMessage = cptkNoSectionsMessage;
window.cptkSupportedSections = cptkSupportedSections;
