/** Integrations panel: definitions, instances, commands, tenant credentials, vault. */

let integrationsDefinitionsTable = null;
let integrationsDefinitionsSearch = null;
let integrationsInstancesTable = null;
let integrationsCommandsTable = null;
let integrationsCommandsSearch = null;
let integrationsTenantCredsTable = null;
let integrationsPacksTable = null;
let vaultEntriesTable = null;
let integrationsPanelInitialized = false;
let vaultLastRendered = null;
let vaultRefreshChain = Promise.resolve();
const integrationsOpProgress = createOperationProgress("Integrations");

function initIntegrationsPanel() {
  if (integrationsPanelInitialized) return;
  integrationsPanelInitialized = true;

  integrationsDefinitionsTable = new Tabulator("#integrations-definitions-grid", {
    height: "320px",
    layout: "fitColumns",
    selectableRows: true,
    placeholder: "No cached integration definitions — refresh cache",
    columns: [
      {
        formatter: "rowSelection",
        hozAlign: "center",
        headerSort: false,
        width: 44,
        frozen: true,
        title: "",
      },
      { title: "Name", field: "name", minWidth: 160 },
      { title: "Display", field: "display", minWidth: 160 },
      { title: "Category", field: "category", width: 120 },
      { title: "Instances", field: "instance_count", width: 90, hozAlign: "right" },
      {
        title: "Script",
        field: "has_script",
        width: 70,
        formatter: "tickCross",
      },
      {
        title: "Pack",
        field: "pack_name",
        minWidth: 120,
        formatter: (cell) => cell.getValue() || "—",
      },
      {
        title: "System",
        field: "system",
        width: 80,
        formatter: "tickCross",
      },
    ],
  });
  integrationsDefinitionsTable.on("rowSelectionChanged", updateIntegrationsSelectionCount);
  integrationsDefinitionsTable.on("rowDblClick", (_event, row) => {
    void viewIntegrationDefinition(row.getData());
  });
  const definitionsSearchInput = document.getElementById("integrations-definitions-search");
  if (definitionsSearchInput) {
    integrationsDefinitionsSearch = attachGridSearch(integrationsDefinitionsTable, definitionsSearchInput, {
      onSelectionChange: updateIntegrationsSelectionCount,
    });
  }

  integrationsInstancesTable = new Tabulator("#integrations-instances-grid", {
    height: "260px",
    layout: "fitColumns",
    selectableRows: true,
    placeholder: "No cached integration instances",
    columns: [
      {
        formatter: "rowSelection",
        hozAlign: "center",
        headerSort: false,
        width: 44,
        frozen: true,
        title: "",
      },
      { title: "Instance", field: "name", minWidth: 160 },
      { title: "Brand", field: "brand", minWidth: 140 },
      { title: "Enabled", field: "enabled", width: 90 },
      { title: "Engine", field: "engine", width: 120 },
      { title: "Pack", field: "pack_name", minWidth: 120 },
      { title: "System", field: "system", width: 80, formatter: "tickCross" },
    ],
  });
  integrationsInstancesTable.on("rowSelectionChanged", updateIntegrationsInstancesSelectionCount);
  integrationsInstancesTable.on("rowDblClick", (_event, row) => {
    void viewIntegrationInstance(row.getData());
  });

  integrationsCommandsTable = new Tabulator("#integrations-commands-grid", {
    height: "320px",
    layout: "fitColumns",
    selectableRows: true,
    placeholder: "No cached integration commands — refresh cache",
    columns: [
      {
        formatter: "rowSelection",
        hozAlign: "center",
        headerSort: false,
        width: 44,
        frozen: true,
        title: "",
      },
      { title: "Name", field: "name", minWidth: 160 },
      { title: "Display", field: "display", minWidth: 160 },
      { title: "Category", field: "category", width: 120 },
      { title: "Commands", field: "command_count", width: 100, hozAlign: "right" },
      { title: "Feed", field: "feed", width: 70, formatter: "tickCross" },
    ],
  });
  integrationsCommandsTable.on("rowSelectionChanged", updateIntegrationsCommandsSelectionCount);
  integrationsCommandsTable.on("rowDblClick", (_event, row) => {
    void viewIntegrationCommands(row.getData());
  });
  const commandsSearchInput = document.getElementById("integrations-commands-search");
  if (commandsSearchInput) {
    integrationsCommandsSearch = attachGridSearch(integrationsCommandsTable, commandsSearchInput, {
      onSelectionChange: updateIntegrationsCommandsSelectionCount,
    });
  }

  integrationsTenantCredsTable = new Tabulator("#integrations-tenant-creds-grid", {
    height: "220px",
    layout: "fitColumns",
    placeholder: "No cached tenant credentials",
    columns: [
      { title: "Name", field: "name", minWidth: 160 },
      { title: "User", field: "user", minWidth: 120 },
      { title: "Workgroup", field: "workgroup", minWidth: 120 },
      { title: "Password", field: "has_password", width: 90, formatter: "tickCross" },
      { title: "Certificate", field: "has_certificate", width: 100, formatter: "tickCross" },
      { title: "Locked", field: "locked", width: 80, formatter: "tickCross" },
    ],
  });

  integrationsPacksTable = new Tabulator("#integrations-packs-grid", {
    height: "220px",
    layout: "fitColumns",
    placeholder: "No cached installed packs",
    columns: [
      { title: "ID", field: "id", minWidth: 140 },
      { title: "Name", field: "name", minWidth: 180 },
      { title: "Version", field: "current_version", width: 100 },
      { title: "Update", field: "update_available", width: 90, formatter: "tickCross" },
    ],
  });

  vaultEntriesTable = new Tabulator("#vault-entries-grid", {
    height: "220px",
    layout: "fitColumns",
    placeholder: "Unlock vault to view entries",
    columns: [
      { title: "Name", field: "name", minWidth: 160 },
      { title: "User", field: "user", minWidth: 120 },
      { title: "Password", field: "has_password", width: 90, formatter: "tickCross" },
      { title: "Certificate", field: "has_certificate", width: 100, formatter: "tickCross" },
      { title: "Notes", field: "notes", minWidth: 180 },
    ],
  });

  document.getElementById("integrations-refresh")?.addEventListener("click", refreshIntegrationsCache);
  document.getElementById("integrations-view")?.addEventListener("click", viewSelectedIntegrationDefinition);
  document.getElementById("integrations-instances-view")?.addEventListener("click", viewSelectedIntegrationInstance);
  document.getElementById("integrations-instances-select-none")?.addEventListener("click", () => {
    integrationsInstancesTable?.deselectRow();
    updateIntegrationsInstancesSelectionCount();
  });
  document.getElementById("integrations-commands-view")?.addEventListener("click", viewSelectedIntegrationCommands);
  document.getElementById("integrations-commands-select-none")?.addEventListener("click", () => {
    if (integrationsCommandsSearch) {
      integrationsCommandsSearch.clearSelection();
    } else {
      integrationsCommandsTable?.deselectRow();
    }
    updateIntegrationsCommandsSelectionCount();
  });
  document.getElementById("integrations-select-none")?.addEventListener("click", () => {
    if (integrationsDefinitionsSearch) {
      integrationsDefinitionsSearch.clearSelection();
    } else {
      integrationsDefinitionsTable?.deselectRow();
    }
    updateIntegrationsSelectionCount();
  });
  document.getElementById("integrations-delete")?.addEventListener("click", deleteSelectedIntegrations);
  document.getElementById("integrations-copy")?.addEventListener("click", (event) => {
    copySelectedIntegrations(event.currentTarget);
  });
  bindIntegrationsCopyOptionExclusivity();

  document.getElementById("vault-unlock-btn")?.addEventListener("click", unlockVault);
  document.getElementById("vault-lock-btn")?.addEventListener("click", lockVault);
  document.getElementById("vault-init-btn")?.addEventListener("click", initVault);
  document.getElementById("vault-add-wrap-btn")?.addEventListener("click", addVaultWrap);
  document.getElementById("vault-revoke-wrap-btn")?.addEventListener("click", revokeVaultWrap);
  document.getElementById("vault-add-entry-btn")?.addEventListener("click", addVaultEntry);

  document.querySelectorAll("#panel-integrations .integrations-tabs .integrations-tab").forEach((button) => {
    button.addEventListener("click", () => switchIntegrationsTab(button.dataset.tab));
  });
}

function getSelectedIntegrationRows() {
  if (integrationsDefinitionsSearch) {
    return integrationsDefinitionsSearch.getSelectedData();
  }
  return integrationsDefinitionsTable ? integrationsDefinitionsTable.getSelectedData() : [];
}

function activeIntegrationsProfile() {
  return document.getElementById("active-profile")?.value || "";
}

async function viewIntegrationDefinition(row) {
  const profile = activeIntegrationsProfile();
  const itemId = row?.id || row?.name;
  if (!profile || !itemId) {
    alert("Select a profile and integration definition to view.");
    return;
  }
  await openContentDetailViewer({
    title: row.display || row.name || itemId,
    fetchUrl: `/api/integrations/definitions/${encodeURIComponent(itemId)}?profile=${encodeURIComponent(profile)}`,
    loaderMessage: "Loading integration definition…",
  });
}

async function viewIntegrationInstance(row) {
  const profile = activeIntegrationsProfile();
  const itemId = row?.id || row?.name;
  if (!profile || !itemId) {
    alert("Select a profile and integration instance to view.");
    return;
  }
  await openContentDetailViewer({
    title: row.name || itemId,
    fetchUrl: `/api/integrations/instances/${encodeURIComponent(itemId)}?profile=${encodeURIComponent(profile)}`,
    loaderMessage: "Loading integration instance…",
  });
}

async function viewIntegrationCommands(row) {
  const profile = activeIntegrationsProfile();
  const itemId = row?.id || row?.name;
  if (!profile || !itemId) {
    alert("Select a profile and integration to view commands for.");
    return;
  }
  await openContentDetailViewer({
    title: row.display || row.name || itemId,
    fetchUrl: `/api/integrations/commands/${encodeURIComponent(itemId)}?profile=${encodeURIComponent(profile)}`,
    loaderMessage: "Loading integration commands…",
  });
}

function getSelectedIntegrationInstanceRows() {
  return integrationsInstancesTable ? integrationsInstancesTable.getSelectedData() : [];
}

function getSelectedIntegrationCommandRows() {
  if (integrationsCommandsSearch) {
    return integrationsCommandsSearch.getSelectedData();
  }
  return integrationsCommandsTable ? integrationsCommandsTable.getSelectedData() : [];
}

async function viewSelectedIntegrationInstance() {
  const selected = getSelectedIntegrationInstanceRows();
  if (selected.length !== 1) {
    alert("Select exactly one integration instance to view.");
    return;
  }
  await viewIntegrationInstance(selected[0]);
}

async function viewSelectedIntegrationCommands() {
  const selected = getSelectedIntegrationCommandRows();
  if (selected.length !== 1) {
    alert("Select exactly one integration to view commands for.");
    return;
  }
  await viewIntegrationCommands(selected[0]);
}

function updateIntegrationsInstancesSelectionCount() {
  const el = document.getElementById("integrations-instances-selection-count");
  if (el) el.textContent = `${getSelectedIntegrationInstanceRows().length} selected`;
}

function updateIntegrationsCommandsSelectionCount() {
  const el = document.getElementById("integrations-commands-selection-count");
  if (el) el.textContent = `${getSelectedIntegrationCommandRows().length} selected`;
}

async function viewSelectedIntegrationDefinition() {
  const selected = getSelectedIntegrationRows();
  if (selected.length !== 1) {
    alert("Select exactly one integration definition to view.");
    return;
  }
  await viewIntegrationDefinition(selected[0]);
}

function updateIntegrationsSelectionCount() {
  const el = document.getElementById("integrations-selection-count");
  if (el) el.textContent = `${getSelectedIntegrationRows().length} selected`;
}

function bindIntegrationsCopyOptionExclusivity() {
  const overwriteEl = document.getElementById("integrations-copy-overwrite");
  const stopEl = document.getElementById("integrations-copy-stop");
  if (!overwriteEl || !stopEl) return;
  overwriteEl.addEventListener("change", () => {
    if (overwriteEl.checked) stopEl.checked = false;
  });
  stopEl.addEventListener("change", () => {
    if (stopEl.checked) overwriteEl.checked = false;
  });
}

function integrationsCopyPayload(source, target, integrationIds) {
  return {
    source_profile: source,
    target_profile: target,
    integration_ids: integrationIds,
    overwrite: document.getElementById("integrations-copy-overwrite")?.checked,
    stop_on_conflict: document.getElementById("integrations-copy-stop")?.checked,
  };
}

function integrationsCopyWouldTakeNoAction(plan) {
  if (plan.would_abort) return true;
  return plan.counts.copy === 0 && plan.counts.update === 0;
}

function formatIntegrationsCopySummary(plan) {
  const noAction = integrationsCopyWouldTakeNoAction(plan);
  const names = plan.items.map((item) => item.name).join(", ");
  const lines = [
    noAction
      ? `Copy ${plan.counts.total} integration(s) from ${plan.source_profile} to ${plan.target_profile}:`
      : `Copy ${plan.counts.total} integration(s) from ${plan.source_profile} to ${plan.target_profile}?`,
    "",
    `Names: ${names}`,
  ];
  if (plan.counts.blocked) {
    const blocked = plan.items.filter((item) => item.action === "blocked").map((item) => item.name).join(", ");
    lines.push(`${plan.counts.blocked} integration(s) cannot be copied: ${blocked}`);
  }
  if (plan.counts.conflict) {
    const conflicts = plan.items.filter((item) => item.action === "conflict").map((item) => item.name).join(", ");
    lines.push(`${plan.counts.conflict} integration(s) already exist on target (stop on conflict): ${conflicts}`);
  }
  if (plan.counts.copy || plan.counts.update) {
    lines.push(`${plan.counts.copy} new, ${plan.counts.update} overwrite, ${plan.counts.skip} skip.`);
  }
  lines.push("", plan.would_abort ? "Copy would abort due to conflicts." : "Proceed?");
  return lines.join("\n");
}

function formatIntegrationsDeleteSummary(plan) {
  const names = plan.items.map((item) => item.name).join(", ");
  const lines = [
    `Delete ${plan.counts.total} integration definition(s) from ${plan.profile}?`,
    "",
    `Names: ${names}`,
    "",
    "This permanently removes the integration definition from the tenant (not just instances).",
  ];
  if (plan.has_instance_warnings) {
    for (const warning of plan.warnings || []) {
      const instanceNames = (warning.instance_names || []).filter(Boolean).join(", ");
      lines.push(
        `Warning: ${warning.name} has ${warning.instance_count} instance(s)` +
          (instanceNames ? `: ${instanceNames}` : ""),
      );
    }
  }
  if (plan.counts.blocked) {
    const blocked = plan.items.filter((item) => item.action === "blocked").map((item) => item.name).join(", ");
    lines.push(`${plan.counts.blocked} integration(s) cannot be deleted: ${blocked}`);
  }
  if (plan.counts.not_found) {
    const missing = plan.items.filter((item) => item.action === "not_found").map((item) => item.name).join(", ");
    lines.push(`${plan.counts.not_found} integration(s) were not found: ${missing}`);
  }
  if (plan.counts.delete) {
    lines.push(`${plan.counts.delete} integration definition(s) will be deleted if you continue.`);
  } else {
    lines.push("No integration definitions can be deleted.");
  }
  lines.push("", plan.would_delete ? "Go ahead?" : "No action will be taken.");
  return lines.join("\n");
}

function promptIntegrationsDeleteTypeConfirm(plan) {
  return new Promise((resolve) => {
    const dialog = document.getElementById("integrations-delete-dialog");
    const form = document.getElementById("integrations-delete-form");
    const input = document.getElementById("integrations-delete-confirm-input");
    const submit = document.getElementById("integrations-delete-submit");
    const cancel = document.getElementById("integrations-delete-cancel");
    const text = document.getElementById("integrations-delete-dialog-text");
    let accepted = false;

    text.textContent = `You are about to delete ${plan.counts.delete} integration definition(s) from ${plan.profile}. This cannot be undone. Type DELETE to proceed.`;
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
      if (input.value !== "DELETE") return;
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

async function copySelectedIntegrations(triggerButton = null) {
  const source = document.getElementById("active-profile")?.value;
  const target = document.getElementById("integrations-copy-target")?.value;
  const selected = getSelectedIntegrationRows();
  if (!selected.length) {
    alert("Select one or more integration definitions to copy.");
    return;
  }
  if (!source || !target) {
    alert("Select source and target profiles.");
    return;
  }
  if (source === target) {
    alert("Choose a different target profile.");
    return;
  }

  const integrationIds = selected.map((row) => row.id || row.name);
  const payload = integrationsCopyPayload(source, target, integrationIds);
  const resultEl = document.getElementById("integrations-action-result");

  try {
    const plan = await withLoader(
      () => api("/api/integrations/copy/preview", { method: "POST", body: JSON.stringify(payload) }),
      "Checking copy plan…",
    );
    if (integrationsCopyWouldTakeNoAction(plan)) {
      alert(formatIntegrationsCopySummary(plan));
      return;
    }
    const proceedCopy = await showConfirmDialog({
      title: "Confirm copy",
      message: formatIntegrationsCopySummary(plan),
      proceedLabel: "Copy",
    });
    if (!proceedCopy) return;

    const data = await integrationsOpProgress.runCopy({
      startMessage: `Copying ${integrationIds.length} integration(s) to ${target}…`,
      httpCall: () => api("/api/integrations/copy", { method: "POST", body: JSON.stringify(payload) }),
      loaderMessage: "Copying integrations…",
      busyButton: triggerButton,
      busyLabel: "Copying…",
    });
    resultEl.textContent = JSON.stringify(data, null, 2);
    resultEl.classList.remove("hidden");
    if (typeof showOutcomeDialog === "function" && typeof summarizeBulkCopyResult === "function") {
      showOutcomeDialog(summarizeBulkCopyResult(data, "integration"));
    } else if (data.aborted) {
      alert(data.reason || "Copy was aborted.");
    }
    await reloadIntegrationsAfterMutation("Refreshing integrations cache…");
  } catch (err) {
    if (typeof showOutcomeDialog === "function") {
      showOutcomeDialog({ title: "Copy failed", message: err.message, success: false });
    } else {
      alert(`Copy failed: ${err.message}`);
    }
  }
}

async function deleteSelectedIntegrations() {
  const profile = document.getElementById("active-profile")?.value;
  const selected = getSelectedIntegrationRows();
  if (!selected.length) {
    alert("Select one or more integration definitions to delete.");
    return;
  }

  const integrationIds = selected.map((row) => row.id || row.name);
  const resultEl = document.getElementById("integrations-action-result");

  try {
    const plan = await withLoader(
      () => api("/api/integrations/delete/preview", {
        method: "POST",
        body: JSON.stringify({ profile, integration_ids: integrationIds }),
      }),
      "Checking integrations…",
    );
    if (!plan.would_delete) {
      alert(formatIntegrationsDeleteSummary(plan));
      return;
    }

    const proceedDelete = await showConfirmDialog({
      title: "Confirm delete",
      message: formatIntegrationsDeleteSummary(plan),
      proceedLabel: "Continue",
    });
    if (!proceedDelete) return;

    const typed = await promptIntegrationsDeleteTypeConfirm(plan);
    if (!typed) return;

    const data = await withLoader(
      () => api("/api/integrations/delete", {
        method: "POST",
        body: JSON.stringify({ profile, integration_ids: integrationIds }),
      }),
      "Deleting integrations…",
    );
    resultEl.textContent = JSON.stringify(data, null, 2);
    resultEl.classList.remove("hidden");
    if (typeof showOutcomeDialog === "function" && typeof summarizeBulkDeleteResult === "function") {
      showOutcomeDialog(summarizeBulkDeleteResult(data, "integration"));
    }
    await reloadIntegrationsAfterMutation("Refreshing integrations cache…");
  } catch (err) {
    if (typeof showOutcomeDialog === "function") {
      showOutcomeDialog({ title: "Delete failed", message: err.message, success: false });
    } else {
      alert(`Delete failed: ${err.message}`);
    }
  }
}

function isVaultTabActive() {
  return Boolean(document.querySelector("#panel-integrations .integrations-tab.active[data-tab='vault']"));
}

function switchIntegrationsTab(tabId) {
  document.querySelectorAll("#panel-integrations .integrations-tabs .integrations-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabId);
  });
  document.querySelectorAll("#panel-integrations .integrations-tab-panel").forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.tab !== tabId);
  });
  if (tabId === "vault") {
    refreshVaultStatus();
  }
}

function setVaultSectionVisible(id, visible) {
  const el = document.getElementById(id);
  if (!el) return;
  if (visible) el.classList.remove("hidden");
  else el.classList.add("hidden");
}

function vaultStatusMessage(data) {
  if (!data?.initialized) {
    return "Create a vault to store integration credentials encrypted on this machine.";
  }
  if (data.locked) {
    return `Unlock to view or edit entries · ${data.wrap_count || 0} passphrase slot(s)`;
  }
  return `Session active until ${data.expires_at || "—"}`;
}

function vaultBadgeForData(data, fallback = "loading") {
  if (!data) return fallback;
  if (!data.initialized) return "unset";
  if (data.locked) return "locked";
  return "unlocked";
}

function renderVaultUi(data, { badge } = {}) {
  vaultLastRendered = data;
  const statusEl = document.getElementById("vault-status");
  const wrapsEl = document.getElementById("vault-wraps-meta");
  const badgeEl = document.getElementById("vault-status-badge");
  const badgeState = badge || vaultBadgeForData(data);
  const labels = {
    loading: "Loading",
    unset: "Not initialized",
    locked: "Locked",
    unlocked: "Unlocked",
    error: "Error",
  };

  if (badgeEl) {
    badgeEl.className = `vault-badge vault-badge--${badgeState}`;
    badgeEl.textContent = labels[badgeState] || badgeState;
  }
  if (statusEl) statusEl.textContent = vaultStatusMessage(data);

  const initialized = data?.initialized === true;
  const locked = initialized && data?.locked !== false;
  setVaultSectionVisible("vault-init-section", !initialized);
  setVaultSectionVisible("vault-session-section", initialized);
  setVaultSectionVisible("vault-manage-section", initialized && !locked);
  setVaultSectionVisible("vault-entries-section", initialized && !locked);
  setVaultSectionVisible("vault-wraps-row", initialized);
  setVaultSectionVisible("vault-unlock-block", initialized && locked);
  setVaultSectionVisible("vault-unlock-btn", initialized && locked);
  setVaultSectionVisible("vault-lock-btn", initialized && !locked);

  if (wrapsEl && initialized) {
    wrapsEl.textContent = (data.wrap_aliases || []).join(", ") || "—";
  }
}

async function refreshVaultStatusOnce() {
  if (!vaultLastRendered) {
    const badgeEl = document.getElementById("vault-status-badge");
    const statusEl = document.getElementById("vault-status");
    if (badgeEl) {
      badgeEl.className = "vault-badge vault-badge--loading";
      badgeEl.textContent = "Loading";
    }
    if (statusEl) statusEl.textContent = "Checking vault status…";
  }
  try {
    const data = await api("/api/vault/status");
    renderVaultUi(data);
    if (!data.initialized || data.locked) {
      vaultEntriesTable?.setData([]);
      return;
    }
    const entries = await api("/api/vault/entries");
    vaultEntriesTable?.setData(entries.entries || []);
  } catch (err) {
    const statusEl = document.getElementById("vault-status");
    const badgeEl = document.getElementById("vault-status-badge");
    if (badgeEl) {
      badgeEl.className = "vault-badge vault-badge--error";
      badgeEl.textContent = "Error";
    }
    if (statusEl) statusEl.textContent = `Could not reach vault service: ${err.message}`;
    if (vaultLastRendered) renderVaultUi(vaultLastRendered);
  }
}

function refreshVaultStatus() {
  vaultRefreshChain = vaultRefreshChain
    .catch(() => {})
    .then(() => refreshVaultStatusOnce());
  return vaultRefreshChain;
}

async function loadIntegrationsForProfile() {
  const profile = document.getElementById("active-profile")?.value;
  const meta = document.getElementById("integrations-meta");
  if (!profile) {
    if (meta) meta.textContent = "Select a profile for tenant integration data";
    return;
  }
  if (meta) meta.textContent = "Loading…";
  try {
    const [configurations, instances, commands, tenantCreds, packs] = await Promise.all([
      api(`/api/integrations/configurations?profile=${encodeURIComponent(profile)}`),
      api(`/api/integrations/instances?profile=${encodeURIComponent(profile)}`),
      api(`/api/integrations/commands?profile=${encodeURIComponent(profile)}`),
      api(`/api/integrations/tenant-credentials?profile=${encodeURIComponent(profile)}`),
      api(`/api/integrations/packs?profile=${encodeURIComponent(profile)}`),
    ]);
    integrationsDefinitionsTable?.setData(configurations.configurations || []);
    if (integrationsDefinitionsSearch) {
      integrationsDefinitionsSearch.clearSelection();
      integrationsDefinitionsSearch.applySearch();
    } else {
      integrationsDefinitionsTable?.deselectRow();
    }
    integrationsInstancesTable?.setData(instances.instances || []);
    integrationsInstancesTable?.deselectRow();
    integrationsCommandsTable?.setData(commands.integrations || []);
    if (integrationsCommandsSearch) {
      integrationsCommandsSearch.clearSelection();
      integrationsCommandsSearch.applySearch();
    } else {
      integrationsCommandsTable?.deselectRow();
    }
    integrationsTenantCredsTable?.setData(tenantCreds.credentials || []);
    integrationsPacksTable?.setData(packs.packs || []);
    updateIntegrationsSelectionCount();
    updateIntegrationsInstancesSelectionCount();
    updateIntegrationsCommandsSelectionCount();
    if (meta) {
      meta.textContent =
        `${configurations.count || 0} definition(s) · ${instances.instances?.length || 0} instance(s) · ` +
        `${commands.count || 0} command catalog(s) · ${tenantCreds.count || 0} tenant credential(s) · ` +
        `${packs.count || 0} pack(s)`;
    }
  } catch (err) {
    if (meta) meta.textContent = `Error: ${err.message}`;
  }
}

async function fetchIntegrationsCacheRefresh(profile) {
  if (window.cptkWs?.submitJob && window.cptkWs.isConnected()) {
    await window.cptkWs.submitJob("cache.refresh", { profile, scope: "integrations" });
    return;
  }
  await api("/api/integrations/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile }),
  });
}

async function reloadIntegrationsAfterMutation(loaderMessage = "Refreshing integrations cache…") {
  const profile = document.getElementById("active-profile")?.value;
  if (!profile) return;
  await withLoader(async () => {
    await fetchIntegrationsCacheRefresh(profile);
    await loadIntegrationsForProfile();
  }, loaderMessage);
}

async function refreshIntegrationsCache() {
  await reloadIntegrationsAfterMutation("Refreshing integrations cache…");
}

async function unlockVault() {
  const passphrase = document.getElementById("vault-passphrase")?.value || "";
  await withLoader(async () => {
    await api("/api/vault/unlock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ passphrase }),
    });
    await refreshVaultStatus();
  }, "Unlocking vault…");
}

async function lockVault() {
  await api("/api/vault/lock", { method: "POST" });
  await refreshVaultStatus();
}

async function initVault() {
  const passphrase = document.getElementById("vault-init-passphrase")?.value || "";
  const alias = document.getElementById("vault-init-alias")?.value || "primary";
  if (!passphrase) {
    alert("Initial passphrase is required.");
    return;
  }
  await withLoader(async () => {
    await api("/api/vault/init", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ passphrase, alias }),
    });
    document.getElementById("vault-init-passphrase").value = "";
    await refreshVaultStatus();
  }, "Initializing vault…");
}

async function addVaultWrap() {
  const current = document.getElementById("vault-current-passphrase")?.value || "";
  const next = document.getElementById("vault-new-passphrase")?.value || "";
  const alias = document.getElementById("vault-wrap-alias")?.value || "";
  await withLoader(async () => {
    await api("/api/vault/wraps", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_passphrase: current,
        new_passphrase: next,
        alias,
      }),
    });
    await refreshVaultStatus();
  }, "Adding passphrase slot…");
}

async function revokeVaultWrap() {
  const passphrase = document.getElementById("vault-current-passphrase")?.value || "";
  const alias = document.getElementById("vault-revoke-alias")?.value || "";
  if (!window.confirm(`Revoke passphrase alias "${alias}"?`)) return;
  await withLoader(async () => {
    await api("/api/vault/wraps/revoke", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ passphrase, alias }),
    });
    await refreshVaultStatus();
  }, "Revoking passphrase slot…");
}

async function addVaultEntry() {
  const body = {
    name: document.getElementById("vault-entry-name")?.value || "",
    user: document.getElementById("vault-entry-user")?.value || "",
    password: document.getElementById("vault-entry-password")?.value || "",
    workgroup: document.getElementById("vault-entry-workgroup")?.value || "",
    notes: document.getElementById("vault-entry-notes")?.value || "",
  };
  await withLoader(async () => {
    await api("/api/vault/entries", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    await refreshVaultStatus();
  }, "Adding vault entry…");
}

window.initIntegrationsPanel = initIntegrationsPanel;
window.loadIntegrationsForProfile = loadIntegrationsForProfile;
window.refreshVaultStatus = refreshVaultStatus;
window.isVaultTabActive = isVaultTabActive;
