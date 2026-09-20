/* Cortex PS Toolkit — client shell */

const ROUTES = {
  home: { title: "Overview", panel: "panel-home" },
  credentials: { title: "API Profiles", panel: "panel-credentials" },
  settings: { title: "Settings", panel: "panel-settings" },
  xql: { title: "XQL Query Tool", panel: "panel-xql" },
  playbooks: { title: "Playbook Tools", panel: "panel-playbooks" },
  scripts: { title: "Script Tools", panel: "panel-scripts" },
  lists: { title: "List Tools", panel: "panel-lists" },
  integrations: { title: "Integrations", panel: "panel-integrations" },
  "object-setup": { title: "Object Setup", panel: "panel-object-setup" },
  indicators: { title: "Indicators (IOCs/BIOCs)", panel: "panel-indicators" },
  "system-admin": { title: "User Administration", panel: "panel-system-admin" },
  "design-content": { title: "Object Setup", panel: "panel-object-setup" },
  "platform-admin": { title: "Indicators (IOCs/BIOCs)", panel: "panel-indicators" },
};

let profiles = [];
let listsTable = null;
let listsGridSearch = null;
let playbooksTools = null;
let scriptsTools = null;
let objectSetupTools = null;
let indicatorsTools = null;
let systemAdminTools = null;
let serverOk = false;
let loaderDepth = 0;

const PROFILE_PICKER_ROUTES = new Set([
  "lists",
  "playbooks",
  "scripts",
  "xql",
  "integrations",
  "object-setup",
  "indicators",
  "system-admin",
  "design-content",
  "platform-admin",
]);

function showLoader(message = "") {
  loaderDepth += 1;
  const overlay = document.getElementById("app-loader");
  const text = document.getElementById("app-loader-text");
  if (text) {
    text.textContent = message;
  }
  overlay.classList.remove("hidden");
  overlay.setAttribute("aria-hidden", "false");
  overlay.setAttribute("aria-busy", "true");
}

function hideLoader() {
  loaderDepth = Math.max(0, loaderDepth - 1);
  if (loaderDepth > 0) {
    return;
  }
  const overlay = document.getElementById("app-loader");
  overlay.classList.add("hidden");
  overlay.setAttribute("aria-hidden", "true");
  overlay.removeAttribute("aria-busy");
  const text = document.getElementById("app-loader-text");
  if (text) {
    text.textContent = "";
  }
}

async function withLoader(fn, message = "") {
  showLoader(message);
  try {
    return await fn();
  } finally {
    hideLoader();
  }
}

window.withLoader = withLoader;
window.showLoader = showLoader;
window.hideLoader = hideLoader;

function showConfirmDialog({ title, message, proceedLabel = "Proceed" }) {
  return new Promise((resolve) => {
    const dialog = document.getElementById("confirm-dialog");
    const form = document.getElementById("confirm-dialog-form");
    const titleEl = document.getElementById("confirm-dialog-title");
    const messageEl = document.getElementById("confirm-dialog-message");
    const cancelBtn = document.getElementById("confirm-dialog-cancel");
    const proceedBtn = document.getElementById("confirm-dialog-proceed");
    if (!dialog || !form || !titleEl || !messageEl || !cancelBtn || !proceedBtn) {
      resolve(window.confirm(message));
      return;
    }

    let accepted = false;
    titleEl.textContent = title;
    messageEl.textContent = message;
    proceedBtn.textContent = proceedLabel;

    const cleanup = () => {
      cancelBtn.removeEventListener("click", onCancel);
      form.removeEventListener("submit", onSubmit);
    };
    const onCancel = () => {
      accepted = false;
      dialog.close();
    };
    const onSubmit = (event) => {
      event.preventDefault();
      accepted = true;
      dialog.close();
    };

    cancelBtn.addEventListener("click", onCancel);
    form.addEventListener("submit", onSubmit);
    dialog.addEventListener(
      "close",
      () => {
        cleanup();
        resolve(accepted);
      },
      { once: true },
    );
    dialog.showModal();
    proceedBtn.focus();
  });
}

function showOutcomeDialog({ title, message, success = true }) {
  const dialog = document.getElementById("outcome-dialog");
  const titleEl = document.getElementById("outcome-dialog-title");
  const messageEl = document.getElementById("outcome-dialog-message");
  if (!dialog || !titleEl || !messageEl) {
    window.alert(message);
    return;
  }
  titleEl.textContent = title;
  messageEl.textContent = message;
  dialog.classList.toggle("outcome-success", success);
  dialog.classList.toggle("outcome-failure", !success);
  dialog.showModal();
}

function summarizeBulkCopyResult(data, itemLabel) {
  if (data.aborted) {
    return { success: false, title: "Copy aborted", message: data.reason || "No items were copied." };
  }
  const results = data.results || [];
  const copied = results.filter((row) => row.status === "copied").length;
  const updated = results.filter((row) => row.status === "updated").length;
  const skipped = results.filter((row) => row.status === "skipped").length;
  const failed = results.filter((row) => row.status === "failed").length;
  const parts = [];
  if (copied) parts.push(`${copied} copied`);
  if (updated) parts.push(`${updated} updated`);
  if (skipped) parts.push(`${skipped} skipped`);
  if (failed) parts.push(`${failed} failed`);
  const detail = parts.length ? parts.join(", ") : "No changes";
  return {
    success: failed === 0,
    title: failed ? "Copy completed with errors" : "Copy complete",
    message: `${itemLabel}s: ${detail}.`,
  };
}

function summarizeBulkDeleteResult(data, itemLabel) {
  const results = data.results || [];
  const deleted = results.filter((row) => row.status === "deleted").length;
  const blocked = results.filter(
    (row) => row.status === "blocked_system" || row.status === "blocked",
  ).length;
  const notFound = results.filter((row) => row.status === "not_found").length;
  const failed = results.filter((row) => row.status === "failed").length;
  const parts = [];
  if (deleted) parts.push(`${deleted} deleted`);
  if (blocked) parts.push(`${blocked} blocked`);
  if (notFound) parts.push(`${notFound} not found`);
  if (failed) parts.push(`${failed} failed`);
  const detail = parts.length ? parts.join(", ") : "No changes";
  return {
    success: failed === 0 && deleted > 0,
    title: failed ? "Delete completed with errors" : deleted ? "Delete complete" : "Nothing deleted",
    message: `${itemLabel}s: ${detail}.`,
  };
}

function summarizeComponentCopyResult(data) {
  if (data.aborted) {
    return { success: false, title: "Deep copy aborted", message: data.reason || "No components were copied." };
  }
  const scriptResults = data.script_results || [];
  const playbookResults = data.playbook_results || [];
  const scriptsCopied = scriptResults.filter((row) => row.status === "copied" || row.status === "updated").length;
  const playbooksCopied = playbookResults.filter((row) => row.status === "copied" || row.status === "updated").length;
  const bindingIssues = (data.binding_issues || []).length;
  const scriptFailed = scriptResults.filter((row) => row.status === "failed").length;
  let message = `Scripts: ${scriptsCopied} saved. Playbooks: ${playbooksCopied} saved.`;
  if (bindingIssues) {
    message += ` ${bindingIssues} script binding issue(s) — check server log.`;
  }
  if (scriptFailed) {
    message += ` ${scriptFailed} script(s) failed.`;
  }
  return {
    success: scriptFailed === 0 && bindingIssues === 0,
    title: bindingIssues || scriptFailed ? "Deep copy completed with issues" : "Deep copy complete",
    message,
  };
}

window.showConfirmDialog = showConfirmDialog;
window.showOutcomeDialog = showOutcomeDialog;
window.summarizeBulkCopyResult = summarizeBulkCopyResult;
window.summarizeBulkDeleteResult = summarizeBulkDeleteResult;
window.summarizeComponentCopyResult = summarizeComponentCopyResult;

function apiBase() {
  if (location.protocol === "file:") {
    throw new Error(
      "Open the app through the dev server, not as a file. Run: ./scripts/dev-server.sh then visit http://127.0.0.1:8770/"
    );
  }
  return "";
}

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(`${apiBase()}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
  } catch (err) {
    const hint = serverOk
      ? err.message
      : `${err.message}. Is the dev server running? Start: ./scripts/dev-server.sh (http://127.0.0.1:8770/)`;
    throw new Error(hint);
  }
  const text = await response.text();
  let body = {};
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { error: text.slice(0, 200) || response.statusText };
    }
  }
  if (!response.ok) {
    const wrongServer =
      response.status === 404 && String(body.error || text).includes("File not found")
        ? " Wrong server on this port? Use ./scripts/dev-server.sh (port 8770, not 8765 XQL monitor)."
        : "";
    const message = body.error || response.statusText || `HTTP ${response.status}`;
    throw new Error(`HTTP ${response.status}: ${message}${wrongServer}`);
  }
  if (body && typeof body === "object" && !Array.isArray(body)) {
    return { status_code: response.status, ...body };
  }
  return { status_code: response.status, result: body };
}

async function checkServerHealth() {
  try {
    await api("/api/health");
    serverOk = true;
  } catch {
    serverOk = false;
  }
}

const ROUTE_ALIASES = {
  "design-content": "object-setup",
  "platform-admin": "indicators",
};

function normalizeRoute(route) {
  return ROUTE_ALIASES[route] || route;
}

function routeFromHash() {
  const hash = location.hash.replace(/^#\/?/, "");
  if (!hash) return "home";
  return ROUTES[hash] ? hash : "home";
}

function navigate(route) {
  location.hash = `#/${route}`;
  renderRoute(route);
}

function reloadCurrentRouteData(route) {
  if (route === "credentials" && typeof initCredentialsSection === "function") {
    initCredentialsSection();
  }
  if (route === "lists") {
    loadListsForActiveProfile();
  }
  if (route === "playbooks" && playbooksTools) {
    playbooksTools.loadForActiveProfile();
  }
  if (route === "scripts" && scriptsTools) {
    scriptsTools.loadForActiveProfile();
  }
  if (route === "xql" && typeof loadXqlForActiveProfile === "function") {
    loadXqlForActiveProfile();
  }
  if (route === "settings" && typeof loadSettingsUi === "function") {
    loadSettingsUi();
  }
  if (route === "integrations") {
    if (typeof loadIntegrationsForProfile === "function") {
      loadIntegrationsForProfile();
    }
    if (typeof isVaultTabActive === "function" && isVaultTabActive() && typeof refreshVaultStatus === "function") {
      refreshVaultStatus();
    }
  }
  if ((route === "object-setup" || route === "design-content") && objectSetupTools) {
    objectSetupTools.loadForActiveProfile();
  }
  if ((route === "indicators" || route === "platform-admin") && indicatorsTools) {
    indicatorsTools.loadForActiveProfile();
  }
  if (route === "system-admin" && systemAdminTools) {
    systemAdminTools.loadForActiveProfile();
  }
}

async function ensureRouteMatchesCapabilities(route) {
  if (typeof cptkRefreshProfileCapabilities !== "function") return route;
  const profile = document.getElementById("active-profile")?.value || "";
  const caps = await cptkRefreshProfileCapabilities(profile);
  if (typeof cptkEnsureRouteSupported !== "function") return route;
  return cptkEnsureRouteSupported(caps, route);
}

function renderRoute(route) {
  const spec = ROUTES[route];
  document.getElementById("section-title").textContent = spec.title;
  const normalized = normalizeRoute(route);
  document.querySelectorAll(".rail-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.route === normalized);
  });
  document.querySelector(".rail-logo")?.classList.toggle("active", route === "home");
  document.querySelectorAll(".panel").forEach((panel) => panel.classList.add("hidden"));
  document.getElementById(spec.panel).classList.remove("hidden");
  const profilePicker = document.getElementById("global-profile-picker");
  profilePicker.style.display = PROFILE_PICKER_ROUTES.has(route) ? "" : "none";
  reloadCurrentRouteData(route);
  if (typeof updateActiveProfileContext === "function") {
    updateActiveProfileContext();
  }
  void (async () => {
    const supportedRoute = await ensureRouteMatchesCapabilities(route);
    if (supportedRoute !== route) {
      navigate(supportedRoute);
    }
  })();
}

async function onActiveProfileChanged() {
  const profile = document.getElementById("active-profile")?.value || "";
  if (profile) {
    localStorage.setItem("cptk_active_profile", profile);
  }
  if (typeof cptkRefreshProfileCapabilities === "function") {
    await cptkRefreshProfileCapabilities(profile, { force: true });
  }
  refillCopyTargetSelects();
  const route = routeFromHash();
  const supportedRoute = await ensureRouteMatchesCapabilities(route);
  if (supportedRoute !== route) {
    navigate(supportedRoute);
    return;
  }
  reloadCurrentRouteData(route);
  if (typeof updateActiveProfileContext === "function") {
    updateActiveProfileContext();
  }
}

function populateTargetSelect(select, excludeSlug) {
  if (!select) return;
  const previous = select.value;
  const exclude = excludeSlug ?? document.getElementById("active-profile")?.value ?? "";
  select.innerHTML = "";
  profiles.forEach((profile) => {
    if (profile.slug === exclude) return;
    const label = `${profile.slug} (${profile.tenant_type})`;
    select.append(new Option(label, profile.slug));
  });
  if (previous && [...select.options].some((option) => option.value === previous)) {
    select.value = previous;
  }
}

window.populateTargetSelect = populateTargetSelect;

function refillCopyTargetSelects() {
  const excludeSlug = document.getElementById("active-profile")?.value ?? "";
  [
    "copy-target",
    "playbooks-copy-target",
    "scripts-copy-target",
    "object-setup-copy-target",
    "object-setup-orchestrate-target",
    "indicators-copy-target",
    "integrations-copy-target",
  ].forEach((id) => {
    populateTargetSelect(document.getElementById(id), excludeSlug);
  });
  if (typeof refillAnalysisCopyTargets === "function") {
    refillAnalysisCopyTargets();
  }
  if (typeof updateAllTargetProfileContexts === "function") {
    updateAllTargetProfileContexts();
  }
}

function fillProfileSelects() {
  window.cptkProfiles = profiles;
  const active = document.getElementById("active-profile");
  active.innerHTML = "";
  profiles.forEach((profile) => {
    const label = `${profile.slug} (${profile.tenant_type})`;
    active.append(new Option(label, profile.slug));
  });
  const saved = localStorage.getItem("cptk_active_profile");
  if (saved && profiles.some((p) => p.slug === saved)) {
    active.value = saved;
  }
  refillCopyTargetSelects();
  void (async () => {
    if (typeof cptkRefreshProfileCapabilities === "function") {
      await cptkRefreshProfileCapabilities(active.value || "");
    }
    const route = routeFromHash();
    const supportedRoute = await ensureRouteMatchesCapabilities(route);
    if (supportedRoute !== route) {
      navigate(supportedRoute);
    }
  })();
  if (typeof updateActiveProfileContext === "function") {
    updateActiveProfileContext();
  }
}

async function loadCredentials() {
  const data = await api("/api/credentials");
  profiles = data.profiles || [];
  fillProfileSelects();
}

function activeProfile() {
  return document.getElementById("active-profile").value;
}

function getSelectedLists() {
  if (listsGridSearch) {
    return listsGridSearch.getSelectedData();
  }
  return listsTable ? listsTable.getSelectedData() : [];
}

function updateListsSelectionCount() {
  const el = document.getElementById("lists-selection-count");
  if (!el) return;
  el.textContent = `${getSelectedLists().length} selected`;
}

function initListsGrid() {
  listsTable = new Tabulator("#lists-grid", {
    height: "420px",
    layout: "fitColumns",
    selectableRows: true,
    placeholder: "No cached lists — click Refresh cache",
    columns: [
      {
        formatter: "rowSelection",
        hozAlign: "center",
        headerSort: false,
        width: 44,
        frozen: true,
        title: "",
      },
      { title: "ID", field: "id", width: 180 },
      { title: "Name", field: "name", minWidth: 200 },
      { title: "Type", field: "type", width: 120 },
      {
        title: "System",
        field: "system",
        width: 80,
        hozAlign: "center",
        formatter: (cell) => (cell.getValue() ? "Yes" : ""),
      },
      { title: "Description", field: "description", minWidth: 180 },
      { title: "Modified", field: "modified", width: 180 },
    ],
  });
  listsTable.on("rowSelectionChanged", updateListsSelectionCount);
  listsTable.on("rowDblClick", (_event, row) => {
    void viewList(row.getData());
  });
  const searchInput = document.getElementById("lists-search");
  if (searchInput) {
    listsGridSearch = attachGridSearch(listsTable, searchInput, {
      onSelectionChange: updateListsSelectionCount,
    });
  }
}

function selectAllListsVisible() {
  if (!listsTable) return;
  if (listsGridSearch) {
    listsGridSearch.selectAllVisible();
  } else {
    listsTable.selectRow("active");
    updateListsSelectionCount();
  }
}

function selectAllLists() {
  if (!listsTable) return;
  if (listsGridSearch) {
    listsGridSearch.selectAll();
  } else {
    listsTable.selectRow("all");
    updateListsSelectionCount();
  }
}

function selectNoLists() {
  if (!listsTable) return;
  if (listsGridSearch) {
    listsGridSearch.clearSelection();
  } else {
    listsTable.deselectRow("all");
    updateListsSelectionCount();
  }
}

async function viewList(row) {
  const profile = activeProfile();
  const itemId = row?.id || row?.name;
  if (!profile || !itemId) {
    alert("Select a profile and list to view.");
    return;
  }
  await openContentDetailViewer({
    title: row.name || itemId,
    fetchUrl: `/api/lists/${encodeURIComponent(itemId)}?profile=${encodeURIComponent(profile)}`,
    loaderMessage: "Loading list…",
  });
}

async function viewSelectedList() {
  const selected = getSelectedLists();
  if (selected.length !== 1) {
    alert("Select exactly one list to view.");
    return;
  }
  await viewList(selected[0]);
}

async function loadListsForActiveProfile() {
  const profile = activeProfile();
  if (!profile || !listsTable) return;
  localStorage.setItem("cptk_active_profile", profile);
  document.getElementById("lists-meta").textContent = "Loading…";
  try {
    const data = await withLoader(
      () => api(`/api/lists?profile=${encodeURIComponent(profile)}`),
      "Loading lists…",
    );
    listsTable.setData(data.lists || []);
    if (listsGridSearch) {
      listsGridSearch.clearSelection();
      listsGridSearch.applySearch();
    } else {
      listsTable.deselectRow();
    }
    const metaLine =
      typeof formatCacheMetaLine === "function"
        ? formatCacheMetaLine(data, "list")
        : `${data.count || 0} list(s) · ${data.refreshed_at ? `Cached ${formatLocalDateTime(data.refreshed_at)}` : "Not cached yet"}`;
    document.getElementById("lists-meta").textContent = metaLine;
    updateListsSelectionCount();
  } catch (err) {
    document.getElementById("lists-meta").textContent = `Error: ${err.message}`;
    listsTable.clearData();
    updateListsSelectionCount();
  }
}

async function refreshListsCache() {
  const profile = activeProfile();
  try {
    let data;
    if (window.cptkWs?.isConnected?.()) {
      try {
        const wsResult = await window.cptkWs.submitJob("cache.refresh", { profile, scope: "lists" });
        data = wsResult?.lists || wsResult;
      } catch (wsErr) {
        console.warn("WebSocket cache refresh failed, falling back to REST:", wsErr);
      }
    }
    if (!data) {
      data = await withLoader(
        () =>
          api("/api/lists/refresh", {
            method: "POST",
            body: JSON.stringify({ profile }),
          }),
        "Refreshing lists cache…",
      );
    }
    document.getElementById("lists-meta").textContent =
      `${data.count} list(s) · Refreshed ${data.refreshed_at ? formatLocalDateTime(data.refreshed_at) : "now"}`;
    await loadListsForActiveProfile();
  } catch (err) {
    alert(`Refresh failed: ${err.message}`);
  }
}

function copyOptionsPayload(source, target, listIds) {
  return {
    source_profile: source,
    target_profile: target,
    list_ids: listIds,
    overwrite: document.getElementById("copy-overwrite").checked,
    stop_on_conflict: document.getElementById("copy-stop-on-conflict").checked,
  };
}

function planWouldTakeNoAction(plan) {
  if (plan.would_abort) {
    return true;
  }
  return plan.counts.copy === 0 && plan.counts.update === 0;
}

function formatCopySummary(plan) {
  const noAction = planWouldTakeNoAction(plan);
  const names = plan.items.map((item) => item.name).join(", ");
  const lines = [
    noAction
      ? `Copy ${plan.counts.total} list(s) from ${plan.source_profile} to ${plan.target_profile}:`
      : `Copy ${plan.counts.total} list(s) from ${plan.source_profile} to ${plan.target_profile}?`,
    "",
    `Lists: ${names}`,
    "",
  ];

  if (plan.stop_on_conflict) {
    lines.push("Stop if name exists on target: Yes");
    if (plan.would_abort) {
      const conflictNames = plan.conflicts.map((item) => item.name).join(", ");
      lines.push(`${plan.counts.conflict} list(s) already exist on target: ${conflictNames}`);
    } else {
      lines.push("No name conflicts on target.");
      lines.push(`${plan.counts.copy} new list(s) will be created.`);
    }
  } else if (plan.overwrite) {
    lines.push("Overwrite existing lists: Yes");
    if (plan.counts.update) {
      lines.push(`${plan.counts.update} existing list(s) will be updated.`);
    }
    if (plan.counts.copy) {
      lines.push(`${plan.counts.copy} new list(s) will be created.`);
    }
  } else {
    lines.push("Overwrite existing lists: No");
    if (plan.counts.skip) {
      const skippedNames = plan.items
        .filter((item) => item.action === "skip")
        .map((item) => item.name)
        .join(", ");
      lines.push(`${plan.counts.skip} existing list(s) will be skipped: ${skippedNames}`);
    }
    if (plan.counts.copy) {
      lines.push(`${plan.counts.copy} new list(s) will be created.`);
    }
  }

  lines.push("", noAction ? "No action will be taken." : "Proceed with copy?");
  return lines.join("\n");
}

function bindCopyOptionExclusivity() {
  const overwriteEl = document.getElementById("copy-overwrite");
  const stopEl = document.getElementById("copy-stop-on-conflict");
  overwriteEl.addEventListener("change", () => {
    if (overwriteEl.checked) stopEl.checked = false;
  });
  stopEl.addEventListener("change", () => {
    if (stopEl.checked) overwriteEl.checked = false;
  });
}

function formatDeleteConfirmSummary(plan) {
  const names = plan.items.map((item) => item.name).join(", ");
  const lines = [
    `Delete ${plan.counts.total} list(s) from ${plan.profile}?`,
    "",
    `Lists: ${names}`,
    "",
    "This permanently removes the selected lists from the tenant.",
  ];

  if (plan.counts.blocked_system) {
    const blocked = plan.items
      .filter((item) => item.action === "blocked_system")
      .map((item) => item.name)
      .join(", ");
    lines.push(
      `${plan.counts.blocked_system} system list(s) cannot be deleted and will be reported as blocked: ${blocked}`,
    );
  }
  if (plan.counts.not_found) {
    const missing = plan.items
      .filter((item) => item.action === "not_found")
      .map((item) => item.name)
      .join(", ");
    lines.push(`${plan.counts.not_found} list(s) were not found in cache: ${missing}`);
  }
  if (plan.counts.delete) {
    lines.push(`${plan.counts.delete} list(s) will be deleted if you continue.`);
  } else {
    lines.push("No list(s) can be deleted.");
  }

  lines.push("", plan.would_delete ? "Go ahead?" : "No action will be taken.");
  return lines.join("\n");
}

function promptDeleteTypeConfirm(plan) {
  return new Promise((resolve) => {
    const dialog = document.getElementById("lists-delete-dialog");
    const form = document.getElementById("lists-delete-form");
    const input = document.getElementById("lists-delete-confirm-input");
    const submit = document.getElementById("lists-delete-submit");
    const cancel = document.getElementById("lists-delete-cancel");
    const text = document.getElementById("lists-delete-dialog-text");
    let accepted = false;

    text.textContent = `You are about to delete ${plan.counts.delete} list(s) from ${plan.profile}. This cannot be undone. Type DELETE to proceed.`;
    input.value = "";
    submit.disabled = true;

    const onInput = () => {
      submit.disabled = input.value !== "DELETE";
    };
    const cleanup = () => {
      input.removeEventListener("input", onInput);
      cancel.removeEventListener("click", onCancel);
      form.removeEventListener("submit", onSubmit);
    };
    const onCancel = () => {
      accepted = false;
      dialog.close();
    };
    const onSubmit = (event) => {
      event.preventDefault();
      if (input.value !== "DELETE") {
        return;
      }
      accepted = true;
      dialog.close();
    };

    input.addEventListener("input", onInput);
    cancel.addEventListener("click", onCancel);
    form.addEventListener("submit", onSubmit);
    dialog.addEventListener(
      "close",
      () => {
        cleanup();
        resolve(accepted);
      },
      { once: true },
    );
    dialog.showModal();
    input.focus();
  });
}

async function deleteSelectedLists() {
  const profile = activeProfile();
  const selected = getSelectedLists();
  if (!selected.length) {
    alert("Select one or more lists to delete.");
    return;
  }

  const listIds = selected.map((row) => row.id);
  const resultEl = document.getElementById("delete-result");

  try {
    const plan = await withLoader(
      () =>
        api("/api/lists/delete/preview", {
          method: "POST",
          body: JSON.stringify({ profile, list_ids: listIds }),
        }),
      "Checking lists…",
    );

    if (!plan.would_delete) {
      alert(formatDeleteConfirmSummary(plan));
      return;
    }

    const proceedDelete = await showConfirmDialog({
      title: "Confirm delete",
      message: formatDeleteConfirmSummary(plan),
      proceedLabel: "Continue",
    });
    if (!proceedDelete) {
      return;
    }

    const typed = await promptDeleteTypeConfirm(plan);
    if (!typed) {
      return;
    }

    const data = await withLoader(
      () =>
        api("/api/lists/delete", {
          method: "POST",
          body: JSON.stringify({ profile, list_ids: listIds }),
        }),
      "Deleting lists…",
    );
    resultEl.textContent = JSON.stringify(data, null, 2);
    resultEl.classList.remove("hidden");
    if (typeof showOutcomeDialog === "function" && typeof summarizeBulkDeleteResult === "function") {
      showOutcomeDialog(summarizeBulkDeleteResult(data, "list"));
    }
    await refreshListsCache();
  } catch (err) {
    if (typeof showOutcomeDialog === "function") {
      showOutcomeDialog({ title: "Delete failed", message: err.message, success: false });
    } else {
      alert(`Delete failed: ${err.message}`);
    }
  }
}

async function copySelectedLists(triggerButton = null) {
  const source = activeProfile();
  const target = document.getElementById("copy-target").value;
  const selected = getSelectedLists();
  if (!selected.length) {
    alert("Select one or more lists to copy.");
    return;
  }
  if (source === target) {
    alert("Choose a different target profile.");
    return;
  }

  const listIds = selected.map((row) => row.id);
  const payload = copyOptionsPayload(source, target, listIds);
  const resultEl = document.getElementById("copy-result");

  try {
    const plan = await withLoader(
      () =>
        api("/api/lists/copy/preview", {
          method: "POST",
          body: JSON.stringify(payload),
        }),
      "Checking copy plan…",
    );

    if (planWouldTakeNoAction(plan)) {
      alert(formatCopySummary(plan));
      return;
    }

    const proceedCopy = await showConfirmDialog({
      title: "Confirm copy",
      message: formatCopySummary(plan),
      proceedLabel: "Copy",
    });
    if (!proceedCopy) {
      return;
    }

    const copyProgress = createOperationProgress("Copy lists");
    const data = await copyProgress.runCopy({
      startMessage: `Copying ${listIds.length} list(s) to ${target}…`,
      httpCall: () => api("/api/lists/copy", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
      loaderMessage: "Copying lists…",
      busyButton: triggerButton,
      busyLabel: "Copying…",
    });
    resultEl.textContent = JSON.stringify(data, null, 2);
    resultEl.classList.remove("hidden");
    if (typeof showOutcomeDialog === "function" && typeof summarizeBulkCopyResult === "function") {
      showOutcomeDialog(summarizeBulkCopyResult(data, "list"));
    } else if (data.aborted) {
      alert(data.reason || "Copy was aborted.");
    }
  } catch (err) {
    if (typeof showOutcomeDialog === "function") {
      showOutcomeDialog({ title: "Copy failed", message: err.message, success: false });
    } else {
      alert(`Copy failed: ${err.message}`);
    }
  }
}

function bindEvents() {
  document.querySelectorAll(".rail-btn").forEach((btn) => {
    btn.addEventListener("click", () => navigate(btn.dataset.route));
  });
  document.querySelectorAll(".landing-card-link").forEach((btn) => {
    btn.addEventListener("click", () => navigate(btn.dataset.route));
  });
  window.addEventListener("hashchange", () => renderRoute(routeFromHash()));
  document.getElementById("active-profile").addEventListener("change", () => {
    void onActiveProfileChanged();
  });
  document.getElementById("lists-refresh").addEventListener("click", refreshListsCache);
  document.getElementById("lists-copy").addEventListener("click", (event) => {
    copySelectedLists(event.currentTarget);
  });
  document.getElementById("lists-delete").addEventListener("click", deleteSelectedLists);
  document.getElementById("lists-view")?.addEventListener("click", viewSelectedList);
  document.getElementById("lists-select-all-visible").addEventListener("click", selectAllListsVisible);
  document.getElementById("lists-select-all").addEventListener("click", selectAllLists);
  document.getElementById("lists-select-none").addEventListener("click", selectNoLists);
  bindCopyOptionExclusivity();
  if (typeof bindProfileContextEvents === "function") {
    bindProfileContextEvents();
  }
}

function initContentToolPanels() {
  playbooksTools = initContentTools({
    resource: "playbooks",
    gridSelector: "#playbooks-grid",
    metaId: "playbooks-meta",
    refreshBtnId: "playbooks-refresh",
    selectAllVisibleBtnId: "playbooks-select-all-visible",
    selectAllBtnId: "playbooks-select-all",
    selectNoneBtnId: "playbooks-select-none",
    deleteBtnId: "playbooks-delete",
    copyBtnId: "playbooks-copy",
    selectionCountId: "playbooks-selection-count",
    copyTargetId: "playbooks-copy-target",
    copyOverwriteId: "playbooks-copy-overwrite",
    copyStopId: "playbooks-copy-stop-on-conflict",
    copyResultId: "playbooks-copy-result",
    deleteResultId: "playbooks-delete-result",
    deleteDialogId: "playbooks-delete-dialog",
    deleteFormId: "playbooks-delete-form",
    deleteDialogTextId: "playbooks-delete-dialog-text",
    deleteConfirmInputId: "playbooks-delete-confirm-input",
    deleteSubmitId: "playbooks-delete-submit",
    deleteCancelId: "playbooks-delete-cancel",
    idsKey: "playbook_ids",
    itemLabel: "playbook",
    searchInputId: "playbooks-search",
    columns: [
      { title: "ID", field: "id", width: 180 },
      { title: "Name", field: "name", minWidth: 220 },
      {
        title: "System",
        field: "system",
        width: 80,
        hozAlign: "center",
        formatter: (cell) => (cell.getValue() ? "Yes" : ""),
      },
      { title: "Description", field: "description", minWidth: 180 },
      { title: "Modified", field: "modified", width: 180 },
    ],
  });

  window.playbooksTools = playbooksTools;
  scriptsTools = initContentTools({
    resource: "scripts",
    gridSelector: "#scripts-grid",
    metaId: "scripts-meta",
    refreshBtnId: "scripts-refresh",
    selectAllVisibleBtnId: "scripts-select-all-visible",
    selectAllBtnId: "scripts-select-all",
    selectNoneBtnId: "scripts-select-none",
    deleteBtnId: "scripts-delete",
    copyBtnId: "scripts-copy",
    selectionCountId: "scripts-selection-count",
    copyTargetId: "scripts-copy-target",
    copyOverwriteId: "scripts-copy-overwrite",
    copyStopId: "scripts-copy-stop-on-conflict",
    copyResultId: "scripts-copy-result",
    deleteResultId: "scripts-delete-result",
    deleteDialogId: "scripts-delete-dialog",
    deleteFormId: "scripts-delete-form",
    deleteDialogTextId: "scripts-delete-dialog-text",
    deleteConfirmInputId: "scripts-delete-confirm-input",
    deleteSubmitId: "scripts-delete-submit",
    deleteCancelId: "scripts-delete-cancel",
    idsKey: "script_ids",
    itemLabel: "script",
    searchInputId: "scripts-search",
    viewBtnId: "scripts-view",
    enableRowView: true,
    columns: [
      { title: "ID", field: "id", width: 180 },
      { title: "Name", field: "name", minWidth: 220 },
      { title: "Type", field: "scriptType", width: 120 },
      {
        title: "System",
        field: "system",
        width: 80,
        hozAlign: "center",
        formatter: (cell) => (cell.getValue() ? "Yes" : ""),
      },
      { title: "Description", field: "description", minWidth: 180 },
      { title: "Modified", field: "modified", width: 180 },
    ],
  });
}

async function boot() {
  bindEvents();
  initListsGrid();
  initContentToolPanels();
  if (typeof initXqlPanel === "function") {
    initXqlPanel();
  }
  if (typeof initPlaybooksAnalysisPanel === "function") {
    initPlaybooksAnalysisPanel();
  }
  if (typeof initSettingsUi === "function") {
    initSettingsUi();
  }
  if (typeof initIntegrationsPanel === "function") {
    initIntegrationsPanel();
  }
  if (typeof initObjectSetupUi === "function") {
    objectSetupTools = initObjectSetupUi();
  }
  if (typeof initIndicatorsUi === "function") {
    indicatorsTools = initIndicatorsUi();
  }
  if (typeof initSystemAdminUi === "function") {
    systemAdminTools = initSystemAdminUi();
  }
  await withLoader(async () => {
    await checkServerHealth();
    await loadCredentials();
  }, "Starting…");
  navigate(routeFromHash());
}

boot().catch((err) => {
  document.body.innerHTML = `<pre style="color:#f88;padding:2rem;white-space:pre-wrap">${err.message}</pre>`;
});
