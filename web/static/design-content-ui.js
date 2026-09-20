/** Design-time content: layouts, classifiers, preprocess, incident fields/types. */

const DESIGN_ASSETS = [
  "layouts",
  "classifiers",
  "preprocess",
  "incident-fields",
  "incident-types",
];

function initDesignContentUi() {
  let table = null;
  let gridSearch = null;
  let activeAsset = localStorage.getItem("cptk_design_asset") || "layouts";
  let progressToast = null;

  function activeProfile() {
    return document.getElementById("active-profile").value;
  }

  function getSelectedRows() {
    if (gridSearch) return gridSearch.getSelectedData();
    return table ? table.getSelectedData() : [];
  }

  function updateSelectionCount() {
    const el = document.getElementById("design-selection-count");
    if (el) el.textContent = `${getSelectedRows().length} selected`;
  }

  function formatProgressMessage(event) {
    const elapsed = event.elapsed_seconds != null ? `${event.elapsed_seconds}s` : "";
    const current = event.current || {};
    const parts = [];
    if (current.asset) parts.push(current.asset);
    if (current.step) parts.push(current.step);
    if (current.target_id) parts.push(String(current.target_id));
    if (current.status) parts.push(String(current.status));
    const inFlight = (event.in_flight || []).filter((item) => item.status === "pending" || item.status === "running");
    if (inFlight.length) parts.push(`${inFlight.length} in flight`);
    return `[${elapsed}] ${parts.join(" · ") || "Working…"}`;
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
      title: "Design content",
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

  function jobProgressHandler(event) {
    if (event.phase === "heartbeat" || event.phase === "step" || event.phase === "started") {
      showProgressToast(formatProgressMessage(event));
    }
  }

  async function runLongJob(action, payload) {
    if (window.cptkWs?.isConnected?.()) {
      return window.cptkWs.submitJob(action, payload, {
        onProgress: jobProgressHandler,
        timeoutMs: 900000,
      });
    }
    return api(`/api/design-content/${payload.asset ? `${payload.asset}/copy` : "refresh"}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  function initGrid() {
    table = new Tabulator("#design-content-grid", {
      height: "360px",
      layout: "fitColumns",
      selectableRows: true,
      placeholder: "No cached items — click Refresh cache",
      columns: [
        { formatter: "rowSelection", hozAlign: "center", headerSort: false, width: 44, frozen: true, title: "" },
        { title: "ID", field: "id", minWidth: 180 },
        { title: "Name", field: "name", minWidth: 160 },
        { title: "Type", field: "type", width: 120 },
        { title: "Pack", field: "packID", width: 120 },
      ],
    });
    table.on("rowSelectionChanged", updateSelectionCount);
    const searchInput = document.getElementById("design-content-search");
    if (searchInput) {
      gridSearch = attachGridSearch(table, searchInput, { onSelectionChange: updateSelectionCount });
    }
  }

  async function loadForActiveProfile() {
    const profile = activeProfile();
    if (!profile || !table) return;
    document.getElementById("design-content-meta").textContent = "Loading…";
    try {
      const data = await withLoader(
        () => api(`/api/design-content/${encodeURIComponent(activeAsset)}?profile=${encodeURIComponent(profile)}`),
        `Loading ${activeAsset}…`,
      );
      table.setData(data.items || []);
      if (gridSearch) {
        gridSearch.clearSelection();
        gridSearch.applySearch();
      } else {
        table.deselectRow();
      }
      const metaLine = typeof formatCacheMetaLine === "function"
        ? formatCacheMetaLine(data, activeAsset)
        : `${data.count || 0} item(s) · ${data.refreshed_at ? `Cached ${formatLocalDateTime(data.refreshed_at)}` : "Not cached yet"}`;
      document.getElementById("design-content-meta").textContent = metaLine;
      updateSelectionCount();
    } catch (err) {
      document.getElementById("design-content-meta").textContent = `Error: ${err.message}`;
      table.clearData();
    }
  }

  async function refreshCache() {
    const profile = activeProfile();
    try {
      let data;
      if (window.cptkWs?.isConnected?.()) {
        data = await window.cptkWs.submitJob("design_content.refresh", { profile, asset: activeAsset }, {
          onProgress: jobProgressHandler,
        });
      } else {
        data = await withLoader(
          () => api("/api/design-content/refresh", { method: "POST", body: JSON.stringify({ profile, asset: activeAsset }) }),
          "Refreshing…",
        );
      }
      clearProgressToast();
      document.getElementById("design-content-meta").textContent =
        `${data.count ?? "?"} item(s) · Refreshed ${data.refreshed_at ? formatLocalDateTime(data.refreshed_at) : "now"}`;
      await loadForActiveProfile();
    } catch (err) {
      clearProgressToast();
      alert(`Refresh failed: ${err.message}`);
    }
  }

  async function copySelected() {
    const source = activeProfile();
    const target = document.getElementById("design-copy-target").value;
    const ids = getSelectedRows().map((row) => row.id).filter(Boolean);
    if (!source || !target || !ids.length) {
      alert("Select items and a target profile.");
      return;
    }
    const payload = {
      source_profile: source,
      target_profile: target,
      asset: activeAsset,
      item_ids: ids,
      overwrite: document.getElementById("design-copy-overwrite").checked,
      stop_on_conflict: document.getElementById("design-copy-stop").checked,
    };
    const preview = await api(`/api/design-content/${encodeURIComponent(activeAsset)}/copy/preview`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const proceed = await showConfirmDialog({
      title: "Copy design content",
      message: JSON.stringify(preview.entries, null, 2),
      proceedLabel: "Copy",
    });
    if (!proceed) return;
    try {
      let result;
      if (window.cptkWs?.isConnected?.()) {
        result = await window.cptkWs.submitJob("design_content.copy", payload, {
          onProgress: jobProgressHandler,
          timeoutMs: 900000,
        });
      } else {
        result = await withLoader(
          () => api(`/api/design-content/${encodeURIComponent(activeAsset)}/copy`, { method: "POST", body: JSON.stringify(payload) }),
          "Copying…",
        );
      }
      clearProgressToast();
      const el = document.getElementById("design-copy-result");
      el.textContent = JSON.stringify(result, null, 2);
      el.classList.remove("hidden");
    } catch (err) {
      clearProgressToast();
      alert(`Copy failed: ${err.message}`);
    }
  }

  async function deleteSelected() {
    const profile = activeProfile();
    const ids = getSelectedRows().map((row) => row.id).filter(Boolean);
    if (!profile || !ids.length) {
      alert("Select items to delete.");
      return;
    }
    const accepted = await showConfirmDialog({
      title: "Delete design content",
      message: `Permanently delete ${ids.length} item(s) from ${profile}?`,
      proceedLabel: "Delete",
    });
    if (!accepted) return;
    const result = await withLoader(
      () => api(`/api/design-content/${encodeURIComponent(activeAsset)}/delete`, {
        method: "POST",
        body: JSON.stringify({ profile, item_ids: ids }),
      }),
      "Deleting…",
    );
    document.getElementById("design-delete-result").textContent = JSON.stringify(result, null, 2);
    document.getElementById("design-delete-result").classList.remove("hidden");
    await refreshCache();
  }

  async function orchestrateWorkflow() {
    const source = activeProfile();
    const target = document.getElementById("design-orchestrate-target").value;
    const ids = getSelectedRows().map((row) => row.id).filter(Boolean);
    if (!source || !target || !ids.length) {
      alert("Select items and orchestration target profile.");
      return;
    }
    const selections = { [activeAsset]: ids };
    const payload = {
      source_profile: source,
      target_profile: target,
      selections,
      overwrite: document.getElementById("design-copy-overwrite").checked,
      stop_on_conflict: document.getElementById("design-copy-stop").checked,
    };
    try {
      let result;
      if (window.cptkWs?.isConnected?.()) {
        result = await window.cptkWs.submitJob("design_content.orchestrate", payload, {
          onProgress: jobProgressHandler,
          timeoutMs: 900000,
        });
      } else {
        result = await withLoader(
          () => api("/api/design-content/orchestrate", { method: "POST", body: JSON.stringify(payload) }),
          "Running workflow…",
        );
      }
      clearProgressToast();
      document.getElementById("design-orchestrate-result").textContent = JSON.stringify(result, null, 2);
      document.getElementById("design-orchestrate-result").classList.remove("hidden");
    } catch (err) {
      clearProgressToast();
      alert(`Workflow failed: ${err.message}`);
    }
  }

  function bindAssetTabs() {
    document.querySelectorAll(".design-asset-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".design-asset-tab").forEach((el) => el.classList.remove("active"));
        btn.classList.add("active");
        activeAsset = btn.dataset.asset;
        localStorage.setItem("cptk_design_asset", activeAsset);
        loadForActiveProfile();
      });
    });
    document.querySelector(`.design-asset-tab[data-asset="${activeAsset}"]`)?.classList.add("active");
  }

  function bindControls() {
    document.getElementById("design-content-refresh")?.addEventListener("click", refreshCache);
    document.getElementById("design-content-copy")?.addEventListener("click", copySelected);
    document.getElementById("design-content-delete")?.addEventListener("click", deleteSelected);
    document.getElementById("design-orchestrate")?.addEventListener("click", orchestrateWorkflow);
    document.getElementById("design-select-none")?.addEventListener("click", () => {
      if (gridSearch) gridSearch.clearSelection();
      else table?.deselectRow();
      updateSelectionCount();
    });
  }

  initGrid();
  bindAssetTabs();
  bindControls();
  return { loadForActiveProfile };
}

window.initDesignContentUi = initDesignContentUi;
