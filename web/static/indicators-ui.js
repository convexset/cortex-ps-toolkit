/** Indicators (IOCs / BIOCs). */

const INDICATOR_SECTIONS = ["indicators", "biocs"];

function initIndicatorsUi() {
  let table = null;
  let gridSearch = null;
  let activeSection = localStorage.getItem("cptk_indicators_section") || "indicators";
  let capabilities = null;
  const opProgress = createOperationProgress("Indicators");

  function activeProfile() {
    return document.getElementById("active-profile").value;
  }

  function getSelectedRows() {
    if (gridSearch) return gridSearch.getSelectedData();
    return table ? table.getSelectedData() : [];
  }

  function updateSelectionCount() {
    const el = document.getElementById("indicators-selection-count");
    if (el) el.textContent = `${getSelectedRows().length} selected`;
  }

  function sectionCapabilities() {
    return capabilities?.indicators?.[activeSection] || null;
  }

  function updateActionControls() {
    const caps = sectionCapabilities();
    const canDelete = caps ? caps.delete : true;
    const canCopy = caps ? caps.copy : true;
    document.getElementById("indicators-delete")?.classList.toggle("hidden", !canDelete);
    document.getElementById("indicators-copy-row")?.classList.toggle("hidden", !canCopy);
    const copyBtn = document.getElementById("indicators-copy");
    if (copyBtn) {
      copyBtn.textContent = activeSection === "biocs" ? "Copy selected (BIOCs)" : "Copy selected (IOCs)";
    }
  }

  async function loadCapabilities() {
    const profile = activeProfile();
    capabilities = profile ? await cptkRefreshProfileCapabilities(profile) : null;
    const result = cptkApplyTabCapabilities({
      caps: capabilities,
      groupKey: "indicators",
      sectionIds: INDICATOR_SECTIONS,
      activeId: activeSection,
      storageKey: "cptk_indicators_section",
      tabSelector: ".indicators-tab",
      dataAttr: "section",
    });
    if (result.changed) activeSection = result.active;
    updateActionControls();
    return result;
  }

  function showActionResult(result) {
    const el = document.getElementById("indicators-action-result");
    if (!el) return;
    el.textContent = JSON.stringify(result, null, 2);
    el.classList.remove("hidden");
  }

  function initGrid() {
    table = new Tabulator("#indicators-grid", {
      height: "420px",
      layout: "fitColumns",
      selectableRows: true,
      placeholder: "No cached data — click Refresh",
      columns: [
        { formatter: "rowSelection", hozAlign: "center", headerSort: false, width: 44, frozen: true, title: "" },
        { title: "ID", field: "id", minWidth: 160 },
        { title: "Name", field: "name", minWidth: 180 },
        { title: "Type", field: "type", width: 140 },
      ],
    });
    table.on("rowSelectionChanged", updateSelectionCount);
    const searchInput = document.getElementById("indicators-search");
    if (searchInput && typeof attachGridSearch === "function") {
      gridSearch = attachGridSearch(table, searchInput, { onSelectionChange: updateSelectionCount });
    }
  }

  async function loadForActiveProfile() {
    const profile = activeProfile();
    if (!profile || !table) return;
    const capResult = await loadCapabilities();
    if (capabilities && capResult.supported.length === 0) {
      document.getElementById("indicators-meta").textContent = cptkNoSectionsMessage("indicators");
      table.clearData();
      updateSelectionCount();
      return;
    }
    document.getElementById("indicators-meta").textContent = "Loading…";
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
      document.getElementById("indicators-meta").textContent = metaLine;
      updateSelectionCount();
    } catch (err) {
      document.getElementById("indicators-meta").textContent = `Error: ${err.message}`;
      table.clearData();
    }
  }

  async function refreshCache(allSections = false) {
    const profile = activeProfile();
    if (!profile) return null;
    await loadCapabilities();
    const sections = allSections
      ? cptkSupportedSections(capabilities, "indicators", INDICATOR_SECTIONS)
      : [activeSection];
    if (!sections.length) {
      alert("No indicator sections are available for this platform.");
      return null;
    }
    try {
      const results = [];
      for (const section of sections) {
        const payload = { profile, section };
        let data;
        if (window.cptkWs?.isConnected?.()) {
          data = await window.cptkWs.submitJob("platform_admin.refresh", payload, { timeoutMs: 900000 });
        } else {
          data = await withLoader(
            () => api("/api/platform-admin/refresh", { method: "POST", body: JSON.stringify(payload) }),
            `Refreshing ${section}…`,
          );
        }
        results.push(data);
      }
      await loadForActiveProfile();
      return results.length === 1 ? results[0] : { profile, sections: results };
    } catch (err) {
      alert(`Refresh failed: ${err.message}`);
    }
    return null;
  }

  async function deleteSelected() {
    const profile = activeProfile();
    if (!profile) return;

    if (activeSection === "biocs") {
      const names = getSelectedRows().map((row) => row.name).filter(Boolean);
      if (!names.length) {
        alert("Select BIOCs to delete.");
        return;
      }
      const preview = await api("/api/platform-admin/biocs/delete/preview", {
        method: "POST",
        body: JSON.stringify({ profile, names }),
      });
      const proceed = await showConfirmDialog({
        title: "Delete BIOCs",
        message: JSON.stringify(preview.entries, null, 2),
        proceedLabel: "Delete",
      });
      if (!proceed) return;
      const deletePayload = { profile, names };
      let result;
      if (window.cptkWs?.isConnected?.()) {
        result = await window.cptkWs.submitJob("platform_admin.bioc_delete", deletePayload, { timeoutMs: 900000 });
      } else {
        result = await withLoader(
          () => api("/api/platform-admin/biocs/delete", { method: "POST", body: JSON.stringify(deletePayload) }),
          "Deleting…",
        );
      }
      showActionResult(result);
      await refreshCache();
      return;
    }

    const ids = getSelectedRows().map((row) => row.id).filter(Boolean);
    if (!ids.length) {
      alert("Select indicators to delete.");
      return;
    }
    const proceed = await showConfirmDialog({
      title: "Delete indicators",
      message: `Permanently delete ${ids.length} indicator(s) from ${profile}?`,
      proceedLabel: "Delete",
    });
    if (!proceed) return;
    const deletePayload = { profile, ids };
    let result;
    if (window.cptkWs?.isConnected?.()) {
      result = await window.cptkWs.submitJob("platform_admin.indicator_delete", deletePayload, { timeoutMs: 900000 });
    } else {
      result = await withLoader(
        () => api("/api/platform-admin/indicators/delete", { method: "POST", body: JSON.stringify(deletePayload) }),
        "Deleting…",
      );
    }
    showActionResult(result);
    await refreshCache();
  }

  async function copySelected(triggerButton = null) {
    const source = activeProfile();
    const target = document.getElementById("indicators-copy-target")?.value;
    if (!source || !target) {
      alert("Select a target profile.");
      return;
    }
    const overwrite = document.getElementById("indicators-copy-overwrite")?.checked;
    const stopOnConflict = document.getElementById("indicators-copy-stop")?.checked;

    if (activeSection === "biocs") {
      const names = getSelectedRows().map((row) => row.name).filter(Boolean);
      if (!names.length) {
        alert("Select BIOCs to copy.");
        return;
      }
      const payload = {
        source_profile: source,
        target_profile: target,
        names,
        overwrite,
        stop_on_conflict: stopOnConflict,
      };
      const preview = await withLoader(
        () => api("/api/platform-admin/biocs/copy/preview", {
          method: "POST",
          body: JSON.stringify(payload),
        }),
        "Checking copy plan…",
      );
      const proceed = await showConfirmDialog({
        title: "Copy BIOCs",
        message: JSON.stringify(preview.entries, null, 2),
        proceedLabel: "Copy",
      });
      if (!proceed) return;
      try {
        const result = await opProgress.runCopy({
          startMessage: `Copying ${names.length} BIOC(s) to ${target}…`,
          wsAction: "platform_admin.bioc_copy",
          payload,
          httpCall: () => api("/api/platform-admin/biocs/copy", { method: "POST", body: JSON.stringify(payload) }),
          loaderMessage: "Copying BIOCs…",
          busyButton: triggerButton,
          busyLabel: "Copying…",
        });
        showActionResult(result);
      } catch (err) {
        alert(`Copy failed: ${err.message}`);
      }
      return;
    }

    const ids = getSelectedRows().map((row) => row.id).filter(Boolean);
    if (!ids.length) {
      alert("Select indicators to copy.");
      return;
    }
    const payload = {
      source_profile: source,
      target_profile: target,
      ids,
      overwrite,
      stop_on_conflict: stopOnConflict,
    };
    const preview = await withLoader(
      () => api("/api/platform-admin/indicators/copy/preview", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
      "Checking copy plan…",
    );
    const proceed = await showConfirmDialog({
      title: "Copy indicators",
      message: JSON.stringify(preview.entries, null, 2),
      proceedLabel: "Copy",
    });
    if (!proceed) return;
    try {
      const result = await opProgress.runCopy({
        startMessage: `Copying ${ids.length} indicator(s) to ${target}…`,
        wsAction: "platform_admin.indicator_copy",
        payload,
        httpCall: () => api("/api/platform-admin/indicators/copy", { method: "POST", body: JSON.stringify(payload) }),
        loaderMessage: "Copying indicators…",
        busyButton: triggerButton,
        busyLabel: "Copying…",
      });
      showActionResult(result);
    } catch (err) {
      alert(`Copy failed: ${err.message}`);
    }
  }

  function bindSectionTabs() {
    document.querySelectorAll(".indicators-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".indicators-tab").forEach((el) => el.classList.remove("active"));
        btn.classList.add("active");
        activeSection = btn.dataset.section;
        localStorage.setItem("cptk_indicators_section", activeSection);
        loadForActiveProfile();
      });
    });
    document.querySelector(`.indicators-tab[data-section="${activeSection}"]`)?.classList.add("active");
  }

  function bindControls() {
    document.getElementById("indicators-refresh")?.addEventListener("click", () => refreshCache(false));
    document.getElementById("indicators-refresh-all")?.addEventListener("click", () => refreshCache(true));
    document.getElementById("indicators-delete")?.addEventListener("click", deleteSelected);
    document.getElementById("indicators-copy")?.addEventListener("click", (event) => {
      copySelected(event.currentTarget);
    });
    document.getElementById("indicators-select-none")?.addEventListener("click", () => {
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

window.initIndicatorsUi = initIndicatorsUi;
