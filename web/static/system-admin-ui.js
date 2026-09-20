/** System admin: RBAC users/roles/groups and API keys. */

const SYSTEM_ADMIN_SECTIONS = ["rbac-users", "rbac-roles", "rbac-groups", "api-keys"];

function initSystemAdminUi() {
  let table = null;
  let gridSearch = null;
  let activeSection = localStorage.getItem("cptk_system_admin_section") || "rbac-users";
  let capabilities = null;

  function activeProfile() {
    return document.getElementById("active-profile").value;
  }

  function getSelectedRows() {
    if (gridSearch) return gridSearch.getSelectedData();
    return table ? table.getSelectedData() : [];
  }

  function updateSelectionCount() {
    const el = document.getElementById("system-admin-selection-count");
    if (el) el.textContent = `${getSelectedRows().length} selected`;
  }

  function sectionCapabilities() {
    return capabilities?.system_admin?.[activeSection] || null;
  }

  function updateActionControls() {
    const caps = sectionCapabilities();
    const isApiKeys = activeSection === "api-keys";
    const canDelete = isApiKeys && (!caps || caps.delete);
    const canGenerate = isApiKeys && (!caps || caps.generate);
    document.getElementById("system-admin-list-actions")?.classList.toggle("hidden", !canDelete);
    document.getElementById("system-admin-generate-panel")?.classList.toggle("hidden", !canGenerate);
  }

  async function loadApiKeyRoleOptions() {
    const select = document.getElementById("system-admin-api-key-roles");
    if (!select) return;
    const profile = activeProfile();
    if (!profile || activeSection !== "api-keys") return;
    const selected = new Set([...select.selectedOptions].map((option) => option.value));
    try {
      const data = await api(`/api/platform-admin/rbac-roles?profile=${encodeURIComponent(profile)}`);
      const names = new Set();
      for (const item of data.items || []) {
        const name = item.name || item.id;
        if (name) names.add(name);
      }
      select.replaceChildren();
      [...names].sort((a, b) => a.localeCompare(b)).forEach((name) => {
        select.add(new Option(name, name, false, selected.has(name)));
      });
    } catch (_) {
      select.replaceChildren();
    }
  }

  async function loadCapabilities() {
    const profile = activeProfile();
    capabilities = profile ? await cptkRefreshProfileCapabilities(profile) : null;
    const result = cptkApplyTabCapabilities({
      caps: capabilities,
      groupKey: "system_admin",
      sectionIds: SYSTEM_ADMIN_SECTIONS,
      activeId: activeSection,
      storageKey: "cptk_system_admin_section",
      tabSelector: ".system-admin-tab",
      dataAttr: "section",
    });
    if (result.changed) activeSection = result.active;
    updateActionControls();
    return result;
  }

  function showActionResult(result) {
    const el = document.getElementById("system-admin-action-result");
    if (!el) return;
    el.textContent = JSON.stringify(result, null, 2);
    el.classList.remove("hidden");
  }

  function gridColumns() {
    const selection = {
      formatter: "rowSelection",
      hozAlign: "center",
      headerSort: false,
      width: 44,
      frozen: true,
      title: "",
    };
    if (activeSection === "rbac-users") {
      return [
        selection,
        { title: "Email", field: "user_email", minWidth: 220 },
        { title: "Name", field: "name", minWidth: 160 },
        {
          title: "Role",
          field: "role",
          minWidth: 140,
          formatter: (cell) => cell.getValue() || cell.getRow().getData().role_name || "",
        },
        { title: "Type", field: "user_type", width: 120 },
      ];
    }
    if (activeSection === "api-keys") {
      const formatEpoch = typeof formatEpochMillis === "function"
        ? formatEpochMillis
        : (value, emptyLabel = "—") => (value == null || value === "" ? emptyLabel : String(value));
      return [
        selection,
        {
          title: "Key ID",
          field: "key_id",
          minWidth: 100,
          formatter: (cell) => cell.getValue() || cell.getRow().getData().id || "",
        },
        { title: "Comment", field: "name", minWidth: 180 },
        { title: "Roles", field: "role", minWidth: 140 },
        {
          title: "Expires",
          field: "expiration",
          minWidth: 190,
          sorter: "number",
          formatter: (cell) => formatEpoch(cell.getValue(), "No expiry"),
        },
        {
          title: "Created",
          field: "creation_time",
          minWidth: 190,
          sorter: "number",
          formatter: (cell) => formatEpoch(cell.getValue()),
        },
        { title: "Created by", field: "created_by", minWidth: 160 },
        { title: "Security", field: "security_level", width: 110 },
      ];
    }
    if (activeSection === "rbac-groups") {
      return [
        selection,
        { title: "Group", field: "id", minWidth: 180 },
        { title: "Pretty name", field: "name", minWidth: 180 },
        { title: "Description", field: "description", minWidth: 200 },
      ];
    }
    return [
      selection,
      { title: "ID", field: "id", minWidth: 160 },
      { title: "Name", field: "name", minWidth: 180 },
      { title: "Type / Role", field: "type", width: 140 },
      { title: "Extra", field: "role", width: 120 },
    ];
  }

  function applyGridColumns() {
    if (!table) return;
    table.setColumns(gridColumns());
  }

  function initGrid() {
    table = new Tabulator("#system-admin-grid", {
      height: "420px",
      layout: "fitColumns",
      selectableRows: true,
      placeholder: "No cached data — click Refresh",
      columns: gridColumns(),
    });
    table.on("rowSelectionChanged", updateSelectionCount);
    const searchInput = document.getElementById("system-admin-search");
    if (searchInput && typeof attachGridSearch === "function") {
      gridSearch = attachGridSearch(table, searchInput, { onSelectionChange: updateSelectionCount });
    }
  }

  async function loadForActiveProfile() {
    const profile = activeProfile();
    if (!profile || !table) return;
    const capResult = await loadCapabilities();
    applyGridColumns();
    if (capabilities && capResult.supported.length === 0) {
      document.getElementById("system-admin-meta").textContent = cptkNoSectionsMessage("system_admin");
      table.clearData();
      updateSelectionCount();
      return;
    }
    document.getElementById("system-admin-meta").textContent = "Loading…";
    try {
      const data = await withLoader(
        () => api(`/api/platform-admin/${encodeURIComponent(activeSection)}?profile=${encodeURIComponent(profile)}`),
        `Loading ${activeSection}…`,
      );
      table.setData(data.items || []);
      if (gridSearch) {
        gridSearch.clearSelection();
        gridSearch.applySearch();
      } else {
        table.deselectRow();
      }
      const metaLine = typeof formatCacheMetaLine === "function"
        ? formatCacheMetaLine(data, activeSection)
        : `${data.count || 0} item(s) · ${data.refreshed_at ? `Cached ${formatLocalDateTime(data.refreshed_at)}` : "Not cached yet"}`;
      document.getElementById("system-admin-meta").textContent = metaLine;
      updateSelectionCount();
      if (activeSection === "api-keys") {
        await loadApiKeyRoleOptions();
      }
    } catch (err) {
      document.getElementById("system-admin-meta").textContent = `Error: ${err.message}`;
      table.clearData();
    }
  }

  async function refreshCache(allSections = false) {
    const profile = activeProfile();
    const sections = allSections
      ? SYSTEM_ADMIN_SECTIONS
      : [activeSection];
    try {
      for (const section of sections) {
        await withLoader(
          () => api("/api/platform-admin/refresh", { method: "POST", body: JSON.stringify({ profile, section }) }),
          `Refreshing ${section}…`,
        );
      }
      await loadForActiveProfile();
    } catch (err) {
      alert(`Refresh failed: ${err.message}`);
    }
  }

  async function deleteSelected() {
    const profile = activeProfile();
    if (!profile || activeSection !== "api-keys") return;
    const keyIds = getSelectedRows().map((row) => row.key_id || row.id).filter(Boolean);
    if (keyIds.length !== 1) {
      alert("Select exactly one API key to delete.");
      return;
    }
    const proceed = await showConfirmDialog({
      title: "Delete API key",
      message: `Delete API key ${keyIds[0]} from ${profile}?`,
      proceedLabel: "Delete",
    });
    if (!proceed) return;
    const result = await withLoader(
      () => api("/api/platform-admin/api-keys/delete", {
        method: "POST",
        body: JSON.stringify({ profile, key_id: keyIds[0] }),
      }),
      "Deleting…",
    );
    showActionResult(result);
    await refreshCache();
  }

  async function generateApiKey() {
    const profile = activeProfile();
    if (!profile) return;
    const rolesSelect = document.getElementById("system-admin-api-key-roles");
    const roles = rolesSelect
      ? [...rolesSelect.selectedOptions].map((option) => option.value).filter(Boolean)
      : [];
    if (!roles.length) {
      alert("Select at least one role for the new API key.");
      return;
    }
    const securityLevel = document.getElementById("system-admin-api-key-security")?.value || "standard";
    const comment = document.getElementById("system-admin-api-key-comment")?.value.trim() || "cortex-ps-toolkit";
    const expirationInput = document.getElementById("system-admin-api-key-expiration")?.value;
    const payload = { profile, roles, security_level: securityLevel, comment };
    if (expirationInput) {
      const expirationMs = new Date(expirationInput).getTime();
      if (Number.isFinite(expirationMs)) {
        payload.expiration = expirationMs;
      }
    }
    const result = await withLoader(
      () => api("/api/platform-admin/api-keys/generate", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
      "Generating API key…",
    );
    showActionResult(result);
    await loadForActiveProfile();
  }

  function bindSectionTabs() {
    document.querySelectorAll(".system-admin-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".system-admin-tab").forEach((el) => el.classList.remove("active"));
        btn.classList.add("active");
        activeSection = btn.dataset.section;
        localStorage.setItem("cptk_system_admin_section", activeSection);
        loadForActiveProfile();
      });
    });
    document.querySelector(`.system-admin-tab[data-section="${activeSection}"]`)?.classList.add("active");
  }

  function bindControls() {
    document.getElementById("system-admin-refresh")?.addEventListener("click", () => refreshCache(false));
    document.getElementById("system-admin-refresh-all")?.addEventListener("click", () => refreshCache(true));
    document.getElementById("system-admin-delete")?.addEventListener("click", deleteSelected);
    document.getElementById("system-admin-generate-key")?.addEventListener("click", generateApiKey);
    document.getElementById("system-admin-select-none")?.addEventListener("click", () => {
      if (gridSearch) gridSearch.clearSelection();
      else table?.deselectRow();
      updateSelectionCount();
    });
  }

  initGrid();
  bindSectionTabs();
  bindControls();
  return { loadForActiveProfile };
}

window.initSystemAdminUi = initSystemAdminUi;
