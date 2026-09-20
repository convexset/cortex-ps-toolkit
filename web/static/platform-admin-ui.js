/** Platform admin: correlation rules, IOCs, RBAC, API keys. */

const ADMIN_SECTIONS = [
  "correlation-rules",
  "biocs",
  "indicators",
  "rbac-users",
  "rbac-roles",
  "rbac-groups",
  "api-keys",
];

const ADMIN_DELETABLE = new Set(["correlation-rules", "biocs", "indicators", "api-keys"]);
const ADMIN_COPYABLE = new Set(["correlation-rules"]);

function initPlatformAdminUi() {
  let table = null;
  let gridSearch = null;
  let activeSection = localStorage.getItem("cptk_admin_section") || "correlation-rules";
  let progressToast = null;

  function activeProfile() {
    return document.getElementById("active-profile").value;
  }

  function getSelectedRows() {
    if (gridSearch) return gridSearch.getSelectedData();
    return table ? table.getSelectedData() : [];
  }

  function updateSelectionCount() {
    const el = document.getElementById("platform-admin-selection-count");
    if (el) el.textContent = `${getSelectedRows().length} selected`;
  }

  function selectedNames() {
    return getSelectedRows().map((row) => row.name).filter(Boolean);
  }

  function selectedIds() {
    return getSelectedRows().map((row) => row.id).filter(Boolean);
  }

  function selectedKeyIds() {
    return getSelectedRows().map((row) => row.key_id || row.id).filter(Boolean);
  }

  function showActionResult(result) {
    const el = document.getElementById("platform-admin-action-result");
    if (!el) return;
    el.textContent = JSON.stringify(result, null, 2);
    el.classList.remove("hidden");
  }

  function updateActionControls() {
    const deletable = ADMIN_DELETABLE.has(activeSection);
    const copyable = ADMIN_COPYABLE.has(activeSection);
    const isApiKeys = activeSection === "api-keys";
    document.getElementById("platform-admin-delete")?.classList.toggle("hidden", !deletable);
    document.getElementById("platform-admin-copy-row")?.classList.toggle("hidden", !copyable);
    document.getElementById("platform-admin-generate-key")?.classList.toggle("hidden", !isApiKeys);
    document.getElementById("platform-admin-generate-comment-wrap")?.classList.toggle("hidden", !isApiKeys);
  }

  function formatProgressMessage(event) {
    const elapsed = event.elapsed_seconds != null ? `${event.elapsed_seconds}s` : "";
    const current = event.current || {};
    const parts = [];
    if (current.section) parts.push(current.section);
    if (current.status) parts.push(String(current.status));
    const inFlight = (event.in_flight || []).filter((item) => item.status === "pending" || item.status === "running");
    if (inFlight.length) parts.push(`${inFlight.length} in flight`);
    return `[${elapsed}] ${parts.join(" · ") || "Refreshing…"}`;
  }

  function showProgressToast(message) {
    if (!window.cptkWs?.showToast) return;
    if (progressToast) {
      const msgEl = progressToast.querySelector(".toast-message");
      if (msgEl) msgEl.textContent = message;
      return;
    }
    progressToast = window.cptkWs.showToast({
      level: "info",
      title: "Platform admin",
      message,
      autoDismissMs: 0,
    });
  }

  function clearProgressToast() {
    if (progressToast) {
      progressToast.querySelector(".toast-close")?.click();
      progressToast = null;
    }
  }

  function initGrid() {
    table = new Tabulator("#platform-admin-grid", {
      height: "420px",
      layout: "fitColumns",
      selectableRows: true,
      placeholder: "No cached data — click Refresh",
      columns: [
        { formatter: "rowSelection", hozAlign: "center", headerSort: false, width: 44, frozen: true, title: "" },
        { title: "ID", field: "id", minWidth: 160 },
        { title: "Name", field: "name", minWidth: 180 },
        { title: "Type / Role", field: "type", width: 140 },
        { title: "Extra", field: "role", width: 120 },
      ],
    });
    table.on("rowSelectionChanged", updateSelectionCount);
    const searchInput = document.getElementById("platform-admin-search");
    if (searchInput && typeof attachGridSearch === "function") {
      gridSearch = attachGridSearch(table, searchInput, { onSelectionChange: updateSelectionCount });
    }
  }

  async function loadForActiveProfile() {
    const profile = activeProfile();
    if (!profile || !table) return;
    document.getElementById("platform-admin-meta").textContent = "Loading…";
    updateActionControls();
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
      document.getElementById("platform-admin-meta").textContent = metaLine;
      updateSelectionCount();
    } catch (err) {
      document.getElementById("platform-admin-meta").textContent = `Error: ${err.message}`;
      table.clearData();
    }
  }

  async function refreshCache(allSections = false) {
    const profile = activeProfile();
    try {
      let data;
      const payload = allSections ? { profile } : { profile, section: activeSection };
      if (window.cptkWs?.isConnected?.()) {
        data = await window.cptkWs.submitJob("platform_admin.refresh", payload, {
          onProgress: (event) => {
            if (event.phase === "heartbeat" || event.phase === "step") {
              showProgressToast(formatProgressMessage(event));
            }
          },
          timeoutMs: 900000,
        });
      } else {
        data = await withLoader(
          () => api("/api/platform-admin/refresh", { method: "POST", body: JSON.stringify(payload) }),
          "Refreshing…",
        );
      }
      clearProgressToast();
      await loadForActiveProfile();
      return data;
    } catch (err) {
      clearProgressToast();
      alert(`Refresh failed: ${err.message}`);
    }
    return null;
  }

  async function deleteSelected() {
    const profile = activeProfile();
    if (!profile) return;
    let payload;
    let endpoint;
    let count;
    if (activeSection === "correlation-rules" || activeSection === "biocs") {
      const names = selectedNames();
      if (!names.length) {
        alert("Select items to delete.");
        return;
      }
      count = names.length;
      endpoint = activeSection === "biocs"
        ? "/api/platform-admin/biocs/delete"
        : "/api/platform-admin/correlation-rules/delete";
      payload = activeSection === "biocs" ? { profile, names } : { profile, names };
    } else if (activeSection === "indicators") {
      const ids = selectedIds();
      if (!ids.length) {
        alert("Select indicators to delete.");
        return;
      }
      count = ids.length;
      endpoint = "/api/platform-admin/indicators/delete";
      payload = { profile, ids };
    } else if (activeSection === "api-keys") {
      const keyIds = selectedKeyIds();
      if (keyIds.length !== 1) {
        alert("Select exactly one API key to delete.");
        return;
      }
      count = 1;
      endpoint = "/api/platform-admin/api-keys/delete";
      payload = { profile, key_id: keyIds[0] };
    } else {
      return;
    }
    const accepted = await showConfirmDialog({
      title: "Delete platform admin items",
      message: `Permanently delete ${count} item(s) from ${profile}?`,
      proceedLabel: "Delete",
    });
    if (!accepted) return;
    const result = await withLoader(
      () => api(endpoint, { method: "POST", body: JSON.stringify(payload) }),
      "Deleting…",
    );
    showActionResult(result);
    await refreshCache();
  }

  async function copySelected() {
    const source = activeProfile();
    const target = document.getElementById("platform-admin-copy-target")?.value;
    const names = selectedNames();
    if (!source || !target || !names.length) {
      alert("Select items and a target profile.");
      return;
    }
    const payload = {
      source_profile: source,
      target_profile: target,
      rule_names: names,
      overwrite: document.getElementById("platform-admin-copy-overwrite")?.checked,
      stop_on_conflict: document.getElementById("platform-admin-copy-stop")?.checked,
    };
    const accepted = await showConfirmDialog({
      title: "Copy correlation rules",
      message: `Copy ${names.length} rule(s) from ${source} to ${target}?`,
      proceedLabel: "Copy",
    });
    if (!accepted) return;
    const result = await withLoader(
      () => api("/api/platform-admin/correlation-rules/copy", { method: "POST", body: JSON.stringify(payload) }),
      "Copying…",
    );
    showActionResult(result);
  }

  async function generateApiKey() {
    const profile = activeProfile();
    if (!profile) return;
    const comment = document.getElementById("platform-admin-generate-comment")?.value || "cortex-ps-toolkit";
    const result = await withLoader(
      () => api("/api/platform-admin/api-keys/generate", {
        method: "POST",
        body: JSON.stringify({ profile, comment }),
      }),
      "Generating API key…",
    );
    showActionResult(result);
    await loadForActiveProfile();
  }

  function bindSectionTabs() {
    document.querySelectorAll(".platform-admin-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".platform-admin-tab").forEach((el) => el.classList.remove("active"));
        btn.classList.add("active");
        activeSection = btn.dataset.section;
        localStorage.setItem("cptk_admin_section", activeSection);
        loadForActiveProfile();
      });
    });
    document.querySelector(`.platform-admin-tab[data-section="${activeSection}"]`)?.classList.add("active");
  }

  function bindControls() {
    document.getElementById("platform-admin-refresh")?.addEventListener("click", () => refreshCache(false));
    document.getElementById("platform-admin-refresh-all")?.addEventListener("click", () => refreshCache(true));
    document.getElementById("platform-admin-delete")?.addEventListener("click", deleteSelected);
    document.getElementById("platform-admin-copy")?.addEventListener("click", copySelected);
    document.getElementById("platform-admin-generate-key")?.addEventListener("click", generateApiKey);
    document.getElementById("platform-admin-select-none")?.addEventListener("click", () => {
      if (gridSearch) gridSearch.clearSelection();
      else table?.deselectRow();
      updateSelectionCount();
    });
  }

  initGrid();
  bindSectionTabs();
  bindControls();
  updateActionControls();
  return { loadForActiveProfile };
}

window.initPlatformAdminUi = initPlatformAdminUi;
