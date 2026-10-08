/** Object Setup: incident types, fields, layouts, classifiers, preprocess, correlation rules. */

const OBJECT_SETUP_ASSET_LABELS = {
  "incident-types": "Incident types",
  "incident-fields": "Custom fields",
  layouts: "Layouts",
  classifiers: "Classifiers & mappers",
  preprocess: "Pre-process rules",
  "correlation-rules": "Correlation rules",
};

const OBJECT_SETUP_DESIGN_ASSETS = [
  "incident-types",
  "incident-fields",
  "layouts",
  "classifiers",
  "preprocess",
];

const OBJECT_SETUP_ADMIN_SECTION = "correlation-rules";
const OBJECT_SETUP_ALL_ASSETS = [...OBJECT_SETUP_DESIGN_ASSETS, OBJECT_SETUP_ADMIN_SECTION];

function initObjectSetupUi() {
  let table = null;
  let gridSearch = null;
  let activeAsset = localStorage.getItem("cptk_object_setup_asset") || "incident-types";
  let capabilities = null;
  const opProgress = createOperationProgress("Object Setup");
  const workflowBasket = {
    items: [],
  };

  let lastCacheStatus = null;

  function activeProfile() {
    return document.getElementById("active-profile").value;
  }

  async function loadCacheStatus(profile) {
    if (!profile || typeof api !== "function") return null;
    try {
      lastCacheStatus = await api(`/api/cache/status?profile=${encodeURIComponent(profile)}`);
      return lastCacheStatus;
    } catch (_err) {
      return lastCacheStatus;
    }
  }

  function updateObjectSetupMeta(data) {
    const metaEl = document.getElementById("object-setup-meta");
    if (!metaEl) return;
    const tooltip =
      typeof formatObjectSetupCachesTooltip === "function" && lastCacheStatus
        ? formatObjectSetupCachesTooltip(lastCacheStatus)
        : "";
    if (typeof setCacheMetaElement === "function") {
      setCacheMetaElement(metaEl, data, assetLabel(activeAsset), { tooltip });
      return;
    }
    metaEl.textContent =
      typeof formatCacheMetaLine === "function"
        ? formatCacheMetaLine(data, assetLabel(activeAsset))
        : `${data.count || 0} item(s)`;
  }

  function isAdminAsset() {
    return activeAsset === OBJECT_SETUP_ADMIN_SECTION;
  }

  function getSelectedRows() {
    if (gridSearch) return gridSearch.getSelectedData();
    return table ? table.getSelectedData() : [];
  }

  function updateSelectionCount() {
    const el = document.getElementById("object-setup-selection-count");
    if (el) el.textContent = `${getSelectedRows().length} selected`;
  }

  function assetCapabilities() {
    if (!capabilities?.object_setup) return null;
    return capabilities.object_setup[activeAsset] || null;
  }

  function updateActionControls() {
    const caps = assetCapabilities();
    const canDelete = caps ? caps.delete : true;
    const canCopy = caps ? caps.copy !== false && caps.list : true;
    document.getElementById("object-setup-delete")?.classList.toggle("hidden", !canDelete);
    document.getElementById("object-setup-copy-row")?.classList.toggle("hidden", !canCopy);
  }

  function workflowItemKey(asset, id) {
    return `${asset}:${id}`;
  }

  function assetLabel(asset) {
    return OBJECT_SETUP_ASSET_LABELS[asset] || asset;
  }

  function workflowItemCount() {
    return workflowBasket.items.length;
  }

  function addRowsToWorkflowBasket(rows, asset) {
    let added = 0;
    for (const row of rows) {
      const id = asset === OBJECT_SETUP_ADMIN_SECTION
        ? (row.name || row.id)
        : row.id;
      if (!id) continue;
      const key = workflowItemKey(asset, String(id));
      if (workflowBasket.items.some((item) => item.key === key)) continue;
      workflowBasket.items.push({
        key,
        asset,
        id: String(id),
        name: row.name || String(id),
        type: row.type || assetLabel(asset),
      });
      added += 1;
    }
    return added;
  }

  function selectionsFromBasket(extraItems = []) {
    const items = [...workflowBasket.items, ...extraItems];
    const selections = {};
    for (const item of items) {
      if (item.asset === OBJECT_SETUP_ADMIN_SECTION) continue;
      if (!selections[item.asset]) selections[item.asset] = [];
      if (!selections[item.asset].includes(item.id)) selections[item.asset].push(item.id);
    }
    return selections;
  }

  function correlationNamesFromBasket(extraItems = []) {
    const items = [...workflowBasket.items, ...extraItems];
    return [...new Set(
      items
        .filter((item) => item.asset === OBJECT_SETUP_ADMIN_SECTION)
        .map((item) => item.name || item.id)
        .filter(Boolean),
    )];
  }

  function removeWorkflowItem(key) {
    workflowBasket.items = workflowBasket.items.filter((item) => item.key !== key);
    renderWorkflowSummary();
  }

  function renderWorkflowSummary() {
    const summaryEl = document.getElementById("object-setup-workflow-summary");
    const listEl = document.getElementById("object-setup-workflow-list");
    const count = workflowItemCount();
    if (summaryEl) {
      summaryEl.textContent = count ? `${count} item(s) in bundle` : "Bundle empty";
    }
    if (!listEl) return;
    listEl.replaceChildren();
    if (!count) {
      listEl.classList.add("hidden");
      return;
    }
    listEl.classList.remove("hidden");
    const sorted = [...workflowBasket.items].sort((a, b) => {
      const assetOrder = OBJECT_SETUP_ALL_ASSETS.indexOf(a.asset) - OBJECT_SETUP_ALL_ASSETS.indexOf(b.asset);
      if (assetOrder !== 0) return assetOrder;
      return a.name.localeCompare(b.name);
    });
    for (const item of sorted) {
      const li = document.createElement("li");
      li.className = "workflow-item";
      li.dataset.key = item.key;

      const nameEl = document.createElement("span");
      nameEl.className = "workflow-item-name";
      nameEl.textContent = item.name;
      nameEl.title = item.name;

      const metaEl = document.createElement("span");
      metaEl.className = "workflow-item-meta";
      metaEl.textContent = `${assetLabel(item.asset)} · ${item.type}`;

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "workflow-item-remove";
      removeBtn.textContent = "Remove";
      removeBtn.addEventListener("click", () => removeWorkflowItem(item.key));

      li.append(nameEl, metaEl, removeBtn);
      listEl.append(li);
    }
  }

  function mergeWorkflowSelection() {
    const rows = getSelectedRows();
    if (!rows.length) {
      alert(isAdminAsset() ? "Select correlation rules to add to the bundle." : "Select items to add to the bundle.");
      return false;
    }
    const added = addRowsToWorkflowBasket(rows, activeAsset);
    if (!added) {
      alert("Selected items are already in the bundle.");
      return false;
    }
    return true;
  }

  function objectSetupCopyRequestFields() {
    if (typeof readCopyModeFromRow === "function") {
      const mode = readCopyModeFromRow("object-setup");
      const fields = {
        overwrite: mode.overwrite,
        stop_on_conflict: mode.stop_on_conflict,
        post_copy_diff: mode.post_copy_diff,
      };
      if (mode.copy_mode === "copy_as_new" && mode.rename_suffix) {
        fields.name_suffix = mode.rename_suffix;
      }
      fields.copy_mode = mode.copy_mode;
      fields.rename_suffix = mode.rename_suffix;
      if (mode.rename_map && Object.keys(mode.rename_map).length) {
        fields.rename_map = mode.rename_map;
      }
      return fields;
    }
    return {
      overwrite: document.getElementById("object-setup-copy-overwrite")?.checked,
      stop_on_conflict: document.getElementById("object-setup-copy-stop")?.checked,
      post_copy_diff: document.getElementById("object-setup-copy-post-diff")?.checked ?? false,
    };
  }

  function buildWorkflowPayload(source, target) {
    const extraItems = [];
    for (const row of getSelectedRows()) {
      const id = isAdminAsset() ? (row.name || row.id) : row.id;
      if (!id) continue;
      extraItems.push({
        key: workflowItemKey(activeAsset, String(id)),
        asset: activeAsset,
        id: String(id),
        name: row.name || String(id),
        type: row.type || assetLabel(activeAsset),
      });
    }
    const selections = selectionsFromBasket(extraItems);
    const correlation_rule_names = correlationNamesFromBasket(extraItems);
    const designIds = Object.values(selections).reduce((sum, ids) => sum + (ids?.length || 0), 0);
    const copyFields = objectSetupCopyRequestFields();
    return {
      source_profile: source,
      target_profile: target,
      selections,
      overwrite: copyFields.overwrite,
      stop_on_conflict: copyFields.stop_on_conflict,
      include_correlation_rules: correlation_rule_names.length > 0,
      correlation_rule_names,
      designIds,
      post_copy_diff: copyFields.post_copy_diff,
      name_suffix: copyFields.name_suffix,
      copy_mode: copyFields.copy_mode,
      rename_suffix: copyFields.rename_suffix,
      rename_map: copyFields.rename_map,
    };
  }

  function workflowItemsForSave() {
    return workflowBasket.items.map((item) => ({
      asset: item.asset,
      id: item.id,
      name: item.name,
      type: item.type,
    }));
  }

  function applyResolvedBundleItems(items) {
    workflowBasket.items = (items || []).map((item) => ({
      key: workflowItemKey(item.asset, String(item.id)),
      asset: item.asset,
      id: String(item.id),
      name: item.name || String(item.id),
      type: item.type || assetLabel(item.asset),
    }));
    renderWorkflowSummary();
  }

  async function refreshSavedBundles() {
    const select = document.getElementById("object-setup-bundle-preset");
    const source = activeProfile();
    if (!select || typeof api !== "function") {
      return;
    }
    if (!source) {
      select.replaceChildren();
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "— select source profile —";
      select.appendChild(placeholder);
      return;
    }
    try {
      const data = await api(`/api/object-setup/bundles?profile=${encodeURIComponent(source)}`);
      const bundles = data.bundles || [];
      const current = select.value;
      select.replaceChildren();
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "— select —";
      select.appendChild(placeholder);
      for (const bundle of bundles) {
        const option = document.createElement("option");
        option.value = bundle.id;
        option.textContent = bundle.name || bundle.id;
        option.dataset.name = bundle.name || bundle.id;
        select.appendChild(option);
      }
      if (current && [...select.options].some((opt) => opt.value === current)) {
        select.value = current;
      } else {
        select.value = "";
      }
    } catch (err) {
      console.warn("Could not load saved bundles:", err);
    }
  }

  async function saveCurrentBundle() {
    const name = document.getElementById("object-setup-bundle-id")?.value?.trim();
    const source = activeProfile();
    if (!name) {
      alert("Enter a bundle identifier to save (unique on this source tenant).");
      return;
    }
    if (!workflowItemCount()) {
      alert("Add items to the bundle before saving.");
      return;
    }
    if (!source) {
      alert("Select a source profile.");
      return;
    }
    try {
      const entry = await withLoader(
        () =>
          api("/api/object-setup/bundles", {
            method: "POST",
            body: JSON.stringify({
              name,
              source_profile: source,
              items: workflowItemsForSave(),
            }),
          }),
        "Saving bundle…",
      );
      await refreshSavedBundles();
      if (entry?.id) {
        document.getElementById("object-setup-bundle-preset").value = entry.id;
      }
      if (typeof showActionSuccess === "function") {
        showActionSuccess(`Saved bundle “${entry.name || name}” on ${source}.`, { title: "Bundle saved" });
      }
    } catch (err) {
      if (typeof showActionError === "function") showActionError(err.message, { title: "Save bundle failed" });
      else alert(`Save bundle failed: ${err.message}`);
    }
  }

  async function loadSelectedBundle() {
    const bundleId = document.getElementById("object-setup-bundle-preset")?.value;
    const source = activeProfile();
    if (!bundleId) {
      alert("Select a saved bundle to load.");
      return;
    }
    if (!source) {
      alert("Select a source profile.");
      return;
    }
    try {
      const preset = await api(
        `/api/object-setup/bundles/${encodeURIComponent(bundleId)}?profile=${encodeURIComponent(source)}`,
      );
      document.getElementById("object-setup-bundle-id").value = preset.name || preset.id || "";
      const resolved = await withLoader(
        () =>
          api("/api/object-setup/bundles/resolve", {
            method: "POST",
            body: JSON.stringify({ profile: source, items: preset.items || [] }),
          }),
        "Resolving bundle on source tenant…",
      );
      applyResolvedBundleItems(resolved.items || []);
      if (resolved.missing_count) {
        const missingLines = (resolved.missing || [])
          .slice(0, 8)
          .map((item) => `${assetLabel(item.asset)} · ${item.name}`)
          .join("\n");
        alert(
          `Loaded ${resolved.resolved_count} item(s). ${resolved.missing_count} could not be matched on this source tenant by id or name:\n${missingLines}`,
        );
      } else if (typeof showActionSuccess === "function") {
        showActionSuccess(`Loaded ${resolved.resolved_count} item(s) from “${preset.name}”.`, { title: "Bundle loaded" });
      }
    } catch (err) {
      if (typeof showActionError === "function") showActionError(err.message, { title: "Load bundle failed" });
      else alert(`Load bundle failed: ${err.message}`);
    }
  }

  async function deleteSelectedBundle() {
    const bundleId = document.getElementById("object-setup-bundle-preset")?.value;
    if (!bundleId) {
      alert("Select a saved bundle to delete.");
      return;
    }
    const proceed = await showConfirmDialog({
      title: "Delete saved bundle",
      message: "Remove this saved bundle preset from local storage?",
      proceedLabel: "Delete",
    });
    if (!proceed) return;
    try {
      const source = activeProfile();
      await api(
        `/api/object-setup/bundles/${encodeURIComponent(bundleId)}?profile=${encodeURIComponent(source)}`,
        { method: "DELETE" },
      );
      document.getElementById("object-setup-bundle-preset").value = "";
      await refreshSavedBundles();
    } catch (err) {
      alert(`Delete failed: ${err.message}`);
    }
  }

  async function loadCapabilities() {
    const profile = activeProfile();
    capabilities = profile ? await cptkRefreshProfileCapabilities(profile) : null;
    const result = cptkApplyTabCapabilities({
      caps: capabilities,
      groupKey: "object_setup",
      sectionIds: OBJECT_SETUP_ALL_ASSETS,
      activeId: activeAsset,
      storageKey: "cptk_object_setup_asset",
      tabSelector: ".object-setup-tab",
      dataAttr: "asset",
    });
    if (result.changed) activeAsset = result.active;
    updateActionControls();
    return result;
  }

  function initGrid() {
    table = new Tabulator("#object-setup-grid", {
      height: typeof cptkGridHeight === "function" ? cptkGridHeight("compact") : "320px",
      layout: "fitColumns",
      selectableRows: true,
      placeholder: "No cached items — click Refresh cache",
      columns: cptkEnhanceColumns([
        { formatter: "rowSelection", hozAlign: "center", headerSort: false, width: 44, frozen: true, title: "" },
        { title: "ID", field: "id", minWidth: 180 },
        { title: "Name", field: "name", minWidth: 160 },
        { title: "Type", field: "type", width: 120 },
        { title: "Pack / Role", field: "packID", width: 120, formatter: (cell) => cell.getValue() || cell.getRow().getData().role || "" },
      ]),
    });
    table.on("rowSelectionChanged", updateSelectionCount);
    const searchInput = document.getElementById("object-setup-search");
    if (searchInput && typeof attachGridSearch === "function") {
      gridSearch = attachGridSearch(table, searchInput, { onSelectionChange: updateSelectionCount });
    }
  }

  async function loadForActiveProfile() {
    const profile = activeProfile();
    if (!profile || !table) return;
    const capResult = await loadCapabilities();
    if (capabilities && capResult.supported.length === 0) {
      document.getElementById("object-setup-meta").textContent = cptkNoSectionsMessage("object_setup");
      table.clearData();
      updateSelectionCount();
      return;
    }
    document.getElementById("object-setup-meta").textContent = "Loading…";
    updateActionControls();
    await loadCacheStatus(profile);
    await refreshSavedBundles();
    try {
      const url = isAdminAsset()
        ? `/api/platform-admin/${encodeURIComponent(activeAsset)}?profile=${encodeURIComponent(profile)}`
        : `/api/design-content/${encodeURIComponent(activeAsset)}?profile=${encodeURIComponent(profile)}`;
      const data = await withLoader(() => api(url), `Loading ${activeAsset}…`);
      table.setData(data.items || []);
      if (gridSearch) {
        gridSearch.clearSelection();
        gridSearch.applySearch();
      } else {
        table.deselectRow();
      }
      updateObjectSetupMeta(data);
      updateSelectionCount();
    } catch (err) {
      document.getElementById("object-setup-meta").textContent = `Error: ${err.message}`;
      table.clearData();
    }
  }

  async function refreshCache() {
    const profile = activeProfile();
    const refreshMessage = `Refreshing ${activeAsset}…`;
    try {
      let data;
      if (isAdminAsset()) {
        const payload = { profile, section: activeAsset };
        if (window.cptkWs?.isConnected?.()) {
          data = await window.cptkWs.submitJob(
            "platform_admin.refresh",
            payload,
            opProgress.wsJobOptions({ startMessage: refreshMessage }),
          );
        } else {
          opProgress.show(refreshMessage);
          data = await withLoader(
            () => api("/api/platform-admin/refresh", { method: "POST", body: JSON.stringify(payload) }),
            refreshMessage,
          );
        }
      } else if (window.cptkWs?.isConnected?.()) {
        data = await window.cptkWs.submitJob(
          "design_content.refresh",
          { profile, asset: activeAsset },
          opProgress.wsJobOptions({ startMessage: refreshMessage }),
        );
      } else {
        opProgress.show(refreshMessage);
        data = await withLoader(
          () => api("/api/design-content/refresh", { method: "POST", body: JSON.stringify({ profile, asset: activeAsset }) }),
          refreshMessage,
        );
      }
      await loadCacheStatus(profile);
      await loadForActiveProfile();
      return data;
    } catch (err) {
      alert(`Refresh failed: ${err.message}`);
    } finally {
      opProgress.clear();
    }
    return null;
  }

  async function copySelected(triggerButton = null) {
    const source = activeProfile();
    const target = document.getElementById("object-setup-copy-target")?.value;
    if (!source || !target) {
      alert("Select a target profile.");
      return;
    }
    const copyFields = objectSetupCopyRequestFields();

    if (isAdminAsset()) {
      const names = getSelectedRows().map((row) => row.name).filter(Boolean);
      if (!names.length) {
        alert("Select correlation rules to copy.");
        return;
      }
      const payload = {
        source_profile: source,
        target_profile: target,
        rule_names: names,
        ...copyFields,
      };
      const preview = await withLoader(
        () => api("/api/platform-admin/correlation-rules/copy/preview", {
          method: "POST",
          body: JSON.stringify(payload),
        }),
        "Checking copy plan…",
      );
      const proceed =
        typeof confirmCopyPlan === "function"
          ? await confirmCopyPlan({
              title: "Copy correlation rules",
              preview,
              proceedLabel: "Copy",
              itemLabel: "rule",
              operation: "platform_admin.correlation_copy",
              source_profile: source,
              target_profile: target,
            })
          : typeof confirmOperation === "function"
            ? await confirmOperation({
                title: "Copy correlation rules",
                plan: preview,
                proceedLabel: "Copy",
                itemLabel: "rule",
              })
            : await showConfirmDialog({
                title: "Copy correlation rules",
                message: typeof formatPreviewEntries === "function"
                  ? formatPreviewEntries(preview, { title: "Copy correlation rules", itemLabel: "rule" })
                  : JSON.stringify(preview.entries, null, 2),
                proceedLabel: "Copy",
              });
      if (!proceed) return;
      try {
        const result = await opProgress.runCopy({
          startMessage: `Copying ${names.length} correlation rule(s) to ${target}…`,
          wsAction: "platform_admin.correlation_copy",
          payload,
          httpCall: () => api("/api/platform-admin/correlation-rules/copy", { method: "POST", body: JSON.stringify(payload) }),
          loaderMessage: "Copying correlation rules…",
          busyButton: triggerButton,
          busyLabel: "Copying…",
        });
        if (typeof showActionOutcome === "function") {
          showActionOutcome("object-setup-action-result", result, { itemLabel: "rule", operation: "copy" });
        }
      } catch (err) {
        if (typeof showActionError === "function") showActionError(err.message, { title: "Copy failed" });
        else alert(`Copy failed: ${err.message}`);
      }
      return;
    }

    const ids = getSelectedRows().map((row) => row.id).filter(Boolean);
    if (!ids.length) {
      alert("Select items to copy.");
      return;
    }
    const payload = {
      source_profile: source,
      target_profile: target,
      asset: activeAsset,
      item_ids: ids,
      ...copyFields,
    };
    if (typeof promptStaleCacheChoice === "function") {
      const cacheChoice = await promptStaleCacheChoice([
        { profile: source, designAssets: [activeAsset] },
        { profile: target, designAssets: [activeAsset] },
      ]);
      if (cacheChoice === "cancel") {
        return;
      }
    }
    const preview = await withLoader(
      () => api(`/api/design-content/${encodeURIComponent(activeAsset)}/copy/preview`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
      "Checking copy plan…",
    );
    const proceed =
      typeof confirmCopyPlan === "function"
        ? await confirmCopyPlan({
            title: "Copy object setup content",
            preview,
            proceedLabel: "Copy",
            itemLabel: "item",
            operation: "design_content.copy",
            source_profile: source,
            target_profile: target,
          })
        : typeof confirmOperation === "function"
          ? await confirmOperation({
              title: "Copy object setup content",
              plan: preview,
              proceedLabel: "Copy",
              itemLabel: "item",
            })
          : await showConfirmDialog({
              title: "Copy object setup content",
              message: typeof formatPreviewEntries === "function"
                ? formatPreviewEntries(preview, { title: "Copy object setup content", itemLabel: activeAsset })
                : JSON.stringify(preview.entries, null, 2),
              proceedLabel: "Copy",
            });
    if (!proceed) return;
    try {
      const result = await opProgress.runCopy({
        startMessage: `Copying ${ids.length} ${activeAsset} item(s) to ${target}…`,
        wsAction: "design_content.copy",
        payload,
        httpCall: () => api(`/api/design-content/${encodeURIComponent(activeAsset)}/copy`, { method: "POST", body: JSON.stringify(payload) }),
        loaderMessage: `Copying ${activeAsset}…`,
        busyButton: triggerButton,
        busyLabel: "Copying…",
      });
      if (typeof showActionOutcome === "function") {
        showActionOutcome("object-setup-action-result", result, { itemLabel: "item", operation: "copy" });
      }
    } catch (err) {
      if (typeof showActionError === "function") showActionError(err.message, { title: "Copy failed" });
      else alert(`Copy failed: ${err.message}`);
    }
  }

  async function deleteSelected() {
    const profile = activeProfile();
    if (!profile) return;

    if (isAdminAsset()) {
      const names = getSelectedRows().map((row) => row.name).filter(Boolean);
      if (!names.length) {
        alert("Select correlation rules to delete.");
        return;
      }
      const preview = await api("/api/platform-admin/correlation-rules/delete/preview", {
        method: "POST",
        body: JSON.stringify({ profile, names }),
      });
      const proceed =
        typeof confirmDeletePlan === "function"
          ? await confirmDeletePlan({
              title: "Delete correlation rules",
              preview,
              proceedLabel: "Delete",
              itemLabel: "rule",
            })
          : await showConfirmDialog({
              title: "Delete correlation rules",
              message: typeof formatPreviewEntries === "function"
                ? formatPreviewEntries(preview, { title: "Delete correlation rules", itemLabel: "rule" })
                : JSON.stringify(preview.entries, null, 2),
              proceedLabel: "Delete",
            });
      if (!proceed) return;
      const deletePayload = { profile, names };
      try {
        opProgress.show("Deleting correlation rules…");
        let result;
        if (window.cptkWs?.isConnected?.()) {
          result = await window.cptkWs.submitJob(
            "platform_admin.correlation_delete",
            deletePayload,
            opProgress.wsJobOptions({ startMessage: "Deleting correlation rules…" }),
          );
        } else {
          result = await withLoader(
            () => api("/api/platform-admin/correlation-rules/delete", { method: "POST", body: JSON.stringify(deletePayload) }),
            "Deleting…",
          );
        }
        if (typeof showActionOutcome === "function") {
          showActionOutcome("object-setup-action-result", result, { itemLabel: "rule", operation: "delete" });
        }
        await refreshCache();
      } catch (err) {
        if (typeof showActionError === "function") showActionError(err.message, { title: "Delete failed" });
        else alert(`Delete failed: ${err.message}`);
      } finally {
        opProgress.clear();
      }
      return;
    }

    const ids = getSelectedRows().map((row) => row.id).filter(Boolean);
    if (!ids.length) {
      alert("Select items to delete.");
      return;
    }
    const preview = await api(`/api/design-content/${encodeURIComponent(activeAsset)}/delete/preview`, {
      method: "POST",
      body: JSON.stringify({ profile, item_ids: ids }),
    });
    const proceed =
      typeof confirmDeletePlan === "function"
        ? await confirmDeletePlan({
            title: "Delete object setup content",
            preview,
            proceedLabel: "Delete",
            itemLabel: activeAsset,
          })
        : await showConfirmDialog({
            title: "Delete object setup content",
            message: typeof formatPreviewEntries === "function"
              ? formatPreviewEntries(preview, { title: "Delete object setup content", itemLabel: activeAsset })
              : JSON.stringify(preview.entries, null, 2),
            proceedLabel: "Delete",
          });
    if (!proceed) return;
    const deletePayload = { profile, asset: activeAsset, item_ids: ids };
    try {
      opProgress.show(`Deleting ${activeAsset}…`);
      let result;
      if (window.cptkWs?.isConnected?.()) {
        result = await window.cptkWs.submitJob(
          "design_content.delete",
          deletePayload,
          opProgress.wsJobOptions({ startMessage: `Deleting ${activeAsset}…` }),
        );
      } else {
        result = await withLoader(
          () => api(`/api/design-content/${encodeURIComponent(activeAsset)}/delete`, {
            method: "POST",
            body: JSON.stringify({ profile, item_ids: ids }),
          }),
          "Deleting…",
        );
      }
      if (typeof showActionOutcome === "function") {
        showActionOutcome("object-setup-action-result", result, { itemLabel: "item", operation: "delete" });
      }
      await refreshCache();
    } catch (err) {
      if (typeof showActionError === "function") showActionError(err.message, { title: "Delete failed" });
      else alert(`Delete failed: ${err.message}`);
    } finally {
      opProgress.clear();
    }
  }

  async function orchestrateWorkflow(triggerButton = null) {
    const source = activeProfile();
    const target = document.getElementById("object-setup-orchestrate-target")?.value;
    if (!source || !target) {
      alert("Select an Object Bundle Destination profile.");
      return;
    }
    const built = buildWorkflowPayload(source, target);
    if (!built.designIds && !built.correlation_rule_names.length) {
      alert("Add items to the bundle or select rows to copy.");
      return;
    }
    const payload = {
      source_profile: built.source_profile,
      target_profile: built.target_profile,
      selections: built.selections,
      overwrite: built.overwrite,
      stop_on_conflict: built.stop_on_conflict,
      include_correlation_rules: built.include_correlation_rules,
      correlation_rule_names: built.correlation_rule_names,
      post_copy_diff: built.post_copy_diff,
      name_suffix: built.name_suffix,
      copy_mode: built.copy_mode,
      rename_suffix: built.rename_suffix,
    };
    try {
      const result = await opProgress.runCopy({
        startMessage: `Copying Object Bundle ${source} → ${target}…`,
        wsAction: "design_content.orchestrate",
        payload,
        httpCall: () => api("/api/design-content/orchestrate", { method: "POST", body: JSON.stringify(payload) }),
        loaderMessage: "Copying Object Bundle…",
        busyButton: triggerButton,
        busyLabel: "Copying Object Bundle…",
      });
      if (typeof showActionOutcome === "function") {
        showActionOutcome("object-setup-action-result", result, { itemLabel: "bundle item", operation: "copy" });
      }
      workflowBasket.items = [];
      renderWorkflowSummary();
    } catch (err) {
      if (typeof showActionError === "function") showActionError(err.message, { title: "Object Bundle copy failed" });
      else alert(`Object Bundle copy failed: ${err.message}`);
    }
  }

  function bindAssetTabs() {
    document.querySelectorAll(".object-setup-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".object-setup-tab").forEach((el) => el.classList.remove("active"));
        btn.classList.add("active");
        activeAsset = btn.dataset.asset;
        localStorage.setItem("cptk_object_setup_asset", activeAsset);
        loadForActiveProfile();
      });
    });
    document.querySelector(`.object-setup-tab[data-asset="${activeAsset}"]`)?.classList.add("active");
  }

  function bindControls() {
    document.getElementById("object-setup-refresh")?.addEventListener("click", refreshCache);
    document.getElementById("object-setup-copy")?.addEventListener("click", (event) => {
      copySelected(event.currentTarget);
    });
    document.getElementById("object-setup-delete")?.addEventListener("click", deleteSelected);
    document.getElementById("object-setup-orchestrate")?.addEventListener("click", (event) => {
      orchestrateWorkflow(event.currentTarget);
    });
    document.getElementById("object-setup-add-workflow")?.addEventListener("click", () => {
      if (mergeWorkflowSelection()) renderWorkflowSummary();
    });
    document.getElementById("object-setup-clear-workflow")?.addEventListener("click", () => {
      workflowBasket.items = [];
      renderWorkflowSummary();
    });
    document.getElementById("object-setup-save-bundle")?.addEventListener("click", () => {
      void saveCurrentBundle();
    });
    document.getElementById("object-setup-load-bundle")?.addEventListener("click", () => {
      void loadSelectedBundle();
    });
    document.getElementById("object-setup-delete-bundle")?.addEventListener("click", () => {
      void deleteSelectedBundle();
    });
    document.getElementById("object-setup-bundle-preset")?.addEventListener("change", () => {
      const select = document.getElementById("object-setup-bundle-preset");
      const option = select?.selectedOptions?.[0];
      if (!option?.value) return;
      document.getElementById("object-setup-bundle-id").value = option.dataset.name || option.value || "";
    });
    const copyRow = document.getElementById("object-setup-copy-row");
    if (copyRow && typeof appendCopyModeControls === "function") {
      appendCopyModeControls(copyRow, "object-setup");
      copyRow.addEventListener("cptk-open-rename-map", () => {
        const target = document.getElementById("object-setup-copy-target")?.value;
        const rows = getSelectedRows().map((row) => ({
          id: isAdminAsset() ? row.name || row.id : row.id,
          name: row.name || row.id,
        }));
        if (typeof openRenameMapEditor === "function") {
          void openRenameMapEditor("object-setup", {
            items: rows,
            targetProfile: target,
            kind: "design",
            asset: activeAsset,
          });
        }
      });
      copyRow.addEventListener("cptk-copy-rename-changed", () => {
        const target = document.getElementById("object-setup-copy-target")?.value;
        if (typeof scheduleCopyNameCheck === "function") {
          scheduleCopyNameCheck("object-setup", {
            targetProfile: target,
            kind: "design",
            asset: activeAsset,
            items: getSelectedRows().map((row) => ({
              id: isAdminAsset() ? row.name || row.id : row.id,
              name: row.name || row.id,
            })),
          });
        }
      });
    }
    if (typeof bindGridSelectionToolbar === "function") {
      bindGridSelectionToolbar({
        table,
        search: gridSearch,
        visibleBtnId: "object-setup-select-all-visible",
        allBtnId: "object-setup-select-all",
        noneBtnId: "object-setup-select-none",
        onSelectionChange: updateSelectionCount,
      });
    }
  }

  initGrid();
  bindAssetTabs();
  bindControls();
  renderWorkflowSummary();
  void refreshSavedBundles();
  return { loadForActiveProfile, refreshSavedBundles };
}

window.initObjectSetupUi = initObjectSetupUi;
window.initDesignContentUi = initObjectSetupUi;
