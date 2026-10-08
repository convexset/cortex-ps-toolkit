/** Bundles section: basket, catalog, copy, export, playbook dependencies. */

const cptkBundleBasket = { items: [] };

const BUNDLE_CONTENT_ASSETS = ["integrations", "lists", "scripts", "playbooks"];
const BUNDLE_DESIGN_ASSETS = [
  "incident-types",
  "incident-fields",
  "layouts",
  "classifiers",
  "preprocess",
];
const BUNDLE_CORRELATION_ASSET = "correlation-rules";
const BUNDLE_CATALOG_ASSETS = [...BUNDLE_CONTENT_ASSETS, ...BUNDLE_DESIGN_ASSETS, BUNDLE_CORRELATION_ASSET];

const BUNDLE_ASSET_LABELS = {
  integrations: "Integrations",
  lists: "Lists",
  scripts: "Scripts",
  playbooks: "Playbooks",
  "incident-types": "Incident types",
  "incident-fields": "Custom fields",
  layouts: "Layouts",
  classifiers: "Classifiers & mappers",
  preprocess: "Pre-process rules",
  "correlation-rules": "Correlation rules",
};

const bundleUiState = {
  loadedPreset: null,
  snapshotJson: "[]",
  activeCatalogAsset: localStorage.getItem("cptk_bundles_catalog_asset") || "lists",
  dependencyRows: [],
  catalogTable: null,
  catalogSearch: null,
};

function bundleItemKey(asset, id) {
  return `${asset}:${id}`;
}

function basketItemsForApi() {
  return cptkBundleBasket.items.map(({ asset, id, name, type }) => ({
    asset,
    id,
    name,
    type,
  }));
}

function normalizedBasketSnapshot() {
  const rows = basketItemsForApi()
    .map((row) => ({ asset: row.asset, id: String(row.id), name: row.name || "", type: row.type || "" }))
    .sort((a, b) => {
      const c = a.asset.localeCompare(b.asset);
      if (c !== 0) return c;
      return a.id.localeCompare(b.id);
    });
  return JSON.stringify(rows);
}

function isBasketDirty() {
  return normalizedBasketSnapshot() !== bundleUiState.snapshotJson;
}

function markBasketClean() {
  bundleUiState.snapshotJson = normalizedBasketSnapshot();
  updateDirtyUi();
}

function updateDirtyUi() {
  const badge = document.getElementById("bundles-dirty-badge");
  const presetEl = document.getElementById("bundles-loaded-preset");
  if (badge) badge.classList.toggle("hidden", !isBasketDirty());
  if (presetEl) {
    if (bundleUiState.loadedPreset?.id) {
      presetEl.textContent = `Loaded preset: ${bundleUiState.loadedPreset.name || bundleUiState.loadedPreset.id}`;
    } else {
      presetEl.textContent = "";
    }
  }
}

/** Possible basket keys for a catalog row (id vs name differ by asset/API). */
function basketKeysForCatalogRow(asset, row) {
  const keys = new Set();
  const primary = bundleRowId(asset, row);
  if (primary) keys.add(bundleItemKey(asset, primary));
  const id = row?.id != null && String(row.id) ? String(row.id) : "";
  const name = row?.name != null && String(row.name) ? String(row.name) : "";
  if (id) keys.add(bundleItemKey(asset, id));
  if (name) keys.add(bundleItemKey(asset, name));
  return keys;
}

function isInBasket(asset, rowOrId) {
  const keys =
    typeof rowOrId === "object" && rowOrId !== null
      ? basketKeysForCatalogRow(asset, rowOrId)
      : new Set([bundleItemKey(asset, String(rowOrId))]);
  return cptkBundleBasket.items.some((item) => keys.has(item.key));
}

function refreshCatalogRowStyles() {
  const table = bundleUiState.catalogTable;
  if (!table) return;
  const asset = bundleUiState.activeCatalogAsset;
  for (const row of table.getRows()) {
    const data = row.getData();
    const inB = isInBasket(asset, data);
    row.getElement().classList.toggle("in-bundle", inB);
    if (Boolean(data._inBasket) !== inB) {
      row.update({ _inBasket: inB });
    }
  }
}

function renderBundleSummary() {
  const summary = document.getElementById("bundles-workflow-summary");
  const listEl = document.getElementById("bundles-workflow-list");
  if (!summary || !listEl) return;
  const n = cptkBundleBasket.items.length;
  summary.textContent = n ? `${n} item(s) in basket` : "Basket empty";
  listEl.classList.toggle("hidden", n === 0);
  listEl.replaceChildren();
  const sorted = [...cptkBundleBasket.items].sort((a, b) => {
    const ao = BUNDLE_CATALOG_ASSETS.indexOf(a.asset) - BUNDLE_CATALOG_ASSETS.indexOf(b.asset);
    if (ao !== 0) return ao;
    return (a.name || "").localeCompare(b.name || "");
  });
  for (const item of sorted) {
    const li = document.createElement("li");
    li.className = "workflow-item";
    const nameEl = document.createElement("span");
    nameEl.className = "workflow-item-name";
    nameEl.textContent = item.name;
    const metaEl = document.createElement("span");
    metaEl.className = "workflow-item-meta";
    metaEl.textContent = `${BUNDLE_ASSET_LABELS[item.asset] || item.asset} · ${item.type || item.asset}`;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "workflow-item-remove";
    btn.textContent = "Remove";
    btn.addEventListener("click", () => {
      cptkBundleBasket.items = cptkBundleBasket.items.filter((row) => row.key !== item.key);
      renderBundleSummary();
    });
    li.append(nameEl, metaEl, btn);
    listEl.append(li);
  }
  updateDirtyUi();
  refreshCatalogRowStyles();
}

function bundleRowId(asset, row) {
  if (asset === BUNDLE_CORRELATION_ASSET || asset === "integrations") {
    return String(row.name || row.id || "");
  }
  return String(row.id || row.name || "");
}

function cptkAddToBundle(asset, row) {
  const id = bundleRowId(asset, row);
  if (!asset || !id) return false;
  const key = bundleItemKey(asset, id);
  if (cptkBundleBasket.items.some((item) => item.key === key)) return false;
  cptkBundleBasket.items.push({
    key,
    asset,
    id,
    name: row.name || id,
    type: row.type || BUNDLE_ASSET_LABELS[asset] || asset,
  });
  renderBundleSummary();
  return true;
}

window.cptkAddToBundle = cptkAddToBundle;
window.cptkBundleBasket = cptkBundleBasket;

function catalogColumnsForAsset(asset) {
  const inBundleCol = {
    title: "In basket",
    field: "_inBasket",
    width: 90,
    hozAlign: "center",
    formatter: (cell) => {
      const catalogAsset = bundleUiState.activeCatalogAsset;
      const data = cell.getRow().getData();
      return isInBasket(catalogAsset, data) ? "Yes" : "";
    },
  };
  if (BUNDLE_CONTENT_ASSETS.includes(asset)) {
    const cols = {
      integrations: [
        inBundleCol,
        { title: "ID", field: "id", minWidth: 140 },
        { title: "Display", field: "display", minWidth: 160 },
        { title: "Category", field: "category", width: 120 },
        {
          title: "Origin",
          field: "system",
          width: 100,
          formatter: (cell) => {
            const row = cell.getRow().getData();
            if (row.system) return "System";
            if (row.pack_id || row.pack_name) return "Pack";
            return row.has_script ? "Custom" : "Stub";
          },
        },
      ],
      lists: [
        inBundleCol,
        { title: "ID", field: "id", minWidth: 160 },
        { title: "Name", field: "name", minWidth: 160 },
        { title: "Type", field: "type", width: 110 },
      ],
      scripts: [
        inBundleCol,
        { title: "ID", field: "id", minWidth: 160 },
        { title: "Name", field: "name", minWidth: 180 },
        { title: "Origin", field: "origin", width: 120 },
      ],
      playbooks: [
        inBundleCol,
        { title: "ID", field: "id", minWidth: 180 },
        { title: "Name", field: "name", minWidth: 200 },
      ],
    };
    return cols[asset];
  }
  return [
    inBundleCol,
    { title: "ID", field: "id", minWidth: 180 },
    { title: "Name", field: "name", minWidth: 160 },
    { title: "Type", field: "type", width: 120 },
    {
      title: "Pack / Role",
      field: "packID",
      width: 120,
      formatter: (cell) => cell.getValue() || cell.getRow().getData().role || "",
    },
  ];
}

function initBundlesSection() {
  let capabilities = null;

  function activeProfile() {
    return document.getElementById("active-profile")?.value || "";
  }

  function getCatalogSelectedRows() {
    if (bundleUiState.catalogSearch) return bundleUiState.catalogSearch.getSelectedData();
    return bundleUiState.catalogTable ? bundleUiState.catalogTable.getSelectedData() : [];
  }

  function updateCatalogSelectionCount() {
    const el = document.getElementById("bundles-catalog-selection-count");
    if (!el) return;
    const count = getCatalogSelectedRows().length;
    el.textContent = count === 0 ? "None selected" : `${count} selected`;
    el.classList.toggle("has-selection", count > 0);
  }

  function mapCatalogRows(rawRows, asset) {
    return (rawRows || []).map((row) => ({
      ...row,
      _inBasket: isInBasket(asset, row),
    }));
  }

  async function loadCatalogTab(force = false) {
    const profile = activeProfile();
    const metaEl = document.getElementById("bundles-catalog-meta");
    const asset = bundleUiState.activeCatalogAsset;
    if (!profile || !bundleUiState.catalogTable) return;
    if (metaEl) metaEl.textContent = "Loading…";
    try {
      let rows = [];
      let metaLine = "";
      if (asset === "integrations") {
        const data = await api(
          `/api/integrations/configurations?profile=${encodeURIComponent(profile)}`,
        );
        rows = data.configurations || [];
        metaLine =
          typeof formatCacheMetaLine === "function"
            ? formatCacheMetaLine(data, BUNDLE_ASSET_LABELS.integrations)
            : `${data.count || rows.length} definition(s)`;
      } else if (BUNDLE_CONTENT_ASSETS.includes(asset)) {
        const data = await api(`/api/${asset}?profile=${encodeURIComponent(profile)}`);
        rows = data[asset] || [];
        metaLine =
          typeof formatCacheMetaLine === "function"
            ? formatCacheMetaLine(data, BUNDLE_ASSET_LABELS[asset])
            : `${data.count || rows.length} item(s)`;
      } else if (asset === BUNDLE_CORRELATION_ASSET) {
        const data = await api(
          `/api/platform-admin/correlation-rules?profile=${encodeURIComponent(profile)}`,
        );
        rows = data.items || data.correlation_rules || [];
        metaLine = `${rows.length} correlation rule(s)`;
      } else {
        const data = await api(
          `/api/design-content/${encodeURIComponent(asset)}?profile=${encodeURIComponent(profile)}`,
        );
        rows = data.items || [];
        metaLine =
          typeof formatCacheMetaLine === "function"
            ? formatCacheMetaLine(data, BUNDLE_ASSET_LABELS[asset])
            : `${data.count || rows.length} item(s)`;
      }
      bundleUiState.catalogTable.setColumns(
        cptkEnhanceColumns([
          {
            formatter: "rowSelection",
            hozAlign: "center",
            headerSort: false,
            width: 44,
            frozen: true,
            title: "",
          },
          ...catalogColumnsForAsset(asset),
        ]),
      );
      bundleUiState.catalogTable.setData(mapCatalogRows(rows, asset));
      if (bundleUiState.catalogSearch) {
        bundleUiState.catalogSearch.clearSelection();
        bundleUiState.catalogSearch.applySearch();
      } else {
        bundleUiState.catalogTable.deselectRow();
      }
      if (metaEl) metaEl.textContent = metaLine;
      updateCatalogSelectionCount();
      refreshCatalogRowStyles();
    } catch (err) {
      if (metaEl) metaEl.textContent = `Error: ${err.message}`;
      if (force) throw err;
    }
  }

  async function loadCapabilities() {
    const profile = activeProfile();
    capabilities = profile ? await cptkRefreshProfileCapabilities(profile) : null;
    const designIds = [...BUNDLE_DESIGN_ASSETS, BUNDLE_CORRELATION_ASSET];
    const result = cptkApplyTabCapabilities({
      caps: capabilities,
      groupKey: "object_setup",
      sectionIds: designIds,
      activeId: bundleUiState.activeCatalogAsset,
      storageKey: "cptk_bundles_catalog_asset",
      tabSelector: ".bundles-catalog-tab",
      dataAttr: "asset",
    });
    if (result.changed) bundleUiState.activeCatalogAsset = result.active;
    for (const asset of BUNDLE_CONTENT_ASSETS) {
      document
        .querySelector(`.bundles-catalog-tab[data-asset="${asset}"]`)
        ?.classList.remove("hidden");
    }
    return result;
  }

  function initCatalogGrid() {
    bundleUiState.catalogTable = new Tabulator("#bundles-catalog-grid", {
      height: typeof cptkGridHeight === "function" ? cptkGridHeight("compact") : "360px",
      layout: "fitColumns",
      selectableRows: true,
      placeholder: "Select a catalog tab — refresh caches if empty",
      columns: cptkEnhanceColumns(catalogColumnsForAsset(bundleUiState.activeCatalogAsset)),
    });
    bundleUiState.catalogTable.on("rowSelectionChanged", updateCatalogSelectionCount);
    const searchInput = document.getElementById("bundles-catalog-search");
    if (searchInput) {
      bundleUiState.catalogSearch = attachGridSearch(bundleUiState.catalogTable, searchInput, {
        onSelectionChange: updateCatalogSelectionCount,
      });
    }
  }

  function bindCatalogTabs() {
    for (const btn of document.querySelectorAll(".bundles-catalog-tab")) {
      btn.addEventListener("click", async () => {
        const asset = btn.dataset.asset;
        if (!asset) return;
        bundleUiState.activeCatalogAsset = asset;
        localStorage.setItem("cptk_bundles_catalog_asset", asset);
        for (const tab of document.querySelectorAll(".bundles-catalog-tab")) {
          tab.classList.toggle("active", tab.dataset.asset === asset);
        }
        await loadCatalogTab();
      });
    }
    const activeBtn = document.querySelector(
      `.bundles-catalog-tab[data-asset="${bundleUiState.activeCatalogAsset}"]`,
    );
    activeBtn?.classList.add("active");
  }

  async function refreshSavedBundles() {
    const select = document.getElementById("bundles-preset");
    const source = activeProfile();
    if (!select || !source) return;
    const data = await api(`/api/bundles?profile=${encodeURIComponent(source)}`);
    const current = select.value;
    select.replaceChildren();
    select.append(new Option("— select —", ""));
    for (const bundle of data.bundles || []) {
      select.append(new Option(bundle.name || bundle.id, bundle.id));
    }
    if (current && [...select.options].some((opt) => opt.value === current)) {
      select.value = current;
    }
  }

  function clearBasket({ newBasket = false } = {}) {
    cptkBundleBasket.items = [];
    bundleUiState.dependencyRows = [];
    renderDepsList();
    if (newBasket) {
      bundleUiState.loadedPreset = null;
      document.getElementById("bundles-preset").value = "";
      markBasketClean();
    }
    renderBundleSummary();
  }

  async function saveCurrentBundle() {
    const name = document.getElementById("bundles-id")?.value?.trim();
    const source = activeProfile();
    if (!name || !source || !cptkBundleBasket.items.length) {
      alert("Name, source profile, and at least one basket item required.");
      return;
    }
    const entry = await withLoader(
      () =>
        api("/api/bundles", {
          method: "POST",
          body: JSON.stringify({
            name,
            source_profile: source,
            items: basketItemsForApi(),
          }),
        }),
      "Saving bundle…",
    );
    bundleUiState.loadedPreset = { id: entry.id || name, name: entry.name || name };
    markBasketClean();
    await refreshSavedBundles();
    if (entry?.id) document.getElementById("bundles-preset").value = entry.id;
    if (typeof showActionSuccess === "function") {
      showActionSuccess(`Saved bundle “${entry.name || name}”.`, { title: "Bundle saved" });
    }
  }

  async function loadSelectedBundle() {
    const bundleId = document.getElementById("bundles-preset")?.value;
    const source = activeProfile();
    if (!bundleId || !source) return;
    const preset = await api(
      `/api/bundles/${encodeURIComponent(bundleId)}?profile=${encodeURIComponent(source)}`,
    );
    document.getElementById("bundles-id").value = preset.name || preset.id || "";
    const resolved = await withLoader(
      () =>
        api("/api/bundles/resolve", {
          method: "POST",
          body: JSON.stringify({ profile: source, items: preset.items || [] }),
        }),
      "Resolving bundle on source…",
    );
    cptkBundleBasket.items = (resolved.items || []).map((item) => ({
      key: bundleItemKey(item.asset, String(item.id)),
      asset: item.asset,
      id: String(item.id),
      name: item.name || String(item.id),
      type: item.type || BUNDLE_ASSET_LABELS[item.asset] || item.asset,
    }));
    bundleUiState.loadedPreset = { id: preset.id || bundleId, name: preset.name || bundleId };
    markBasketClean();
    renderBundleSummary();
  }

  function renderDepsList() {
    const listEl = document.getElementById("bundles-deps-list");
    if (!listEl) return;
    listEl.replaceChildren();
    for (const row of bundleUiState.dependencyRows) {
      const li = document.createElement("li");
      li.className = "workflow-item";
      if (!row.selectable) li.classList.add("muted");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.disabled = !row.selectable || row.in_bundle;
      cb.checked = false;
      cb.dataset.depKey = `${row.kind}:${row.id || row.name}`;
      const label = document.createElement("label");
      label.textContent = `${row.playbook_name} → ${row.kind} · ${row.name}${
        row.in_bundle ? " (in basket)" : row.reason ? ` — ${row.reason}` : ""
      }`;
      label.prepend(cb);
      li.append(label);
      listEl.append(li);
    }
  }

  async function scanPlaybookDependencies() {
    const source = activeProfile();
    const playbookIds = cptkBundleBasket.items
      .filter((item) => item.asset === "playbooks")
      .map((item) => item.id);
    if (!source || !playbookIds.length) {
      alert("Add at least one playbook to the basket first.");
      return;
    }
    const data = await withLoader(
      () =>
        api("/api/bundles/playbook-dependencies", {
          method: "POST",
          body: JSON.stringify({
            source_profile: source,
            playbook_ids: playbookIds,
            basket_items: basketItemsForApi(),
          }),
        }),
      "Scanning playbook dependencies…",
    );
    bundleUiState.dependencyRows = data.dependencies || [];
    renderDepsList();
  }

  function addSelectedDependencies() {
    let added = 0;
    for (const li of document.querySelectorAll("#bundles-deps-list li")) {
      const cb = li.querySelector('input[type="checkbox"]');
      if (!cb?.checked) continue;
      const row = bundleUiState.dependencyRows.find(
        (dep) => `${dep.kind}:${dep.id || dep.name}` === cb.dataset.depKey,
      );
      if (!row || !row.selectable || row.in_bundle) continue;
      const asset = row.kind === "script" ? "scripts" : "playbooks";
      if (cptkAddToBundle(asset, { id: row.id || row.name, name: row.name })) added += 1;
    }
    if (!added) alert("No new dependencies added.");
  }

  function addCatalogSelectionToBasket() {
    const asset = bundleUiState.activeCatalogAsset;
    const rows = getCatalogSelectedRows();
    if (!rows.length) {
      alert("Select catalog rows to add.");
      return;
    }
    let added = 0;
    for (const row of rows) {
      if (cptkAddToBundle(asset, row)) added += 1;
    }
    if (!added) alert("Selected items are already in the basket.");
  }

  async function refreshAllCaches() {
    const profile = activeProfile();
    if (!profile) return;
    await withLoader(async () => {
      for (const asset of BUNDLE_CONTENT_ASSETS) {
        await api(`/api/${asset}/refresh`, { method: "POST", body: JSON.stringify({ profile }) });
      }
      for (const asset of BUNDLE_DESIGN_ASSETS) {
        await api("/api/design-content/refresh", {
          method: "POST",
          body: JSON.stringify({ profile, asset }),
        });
      }
      if (
        capabilities?.object_setup?.[BUNDLE_CORRELATION_ASSET]?.list !== false
      ) {
        await api("/api/platform-admin/refresh", {
          method: "POST",
          body: JSON.stringify({ profile, section: "correlation-rules" }),
        });
      }
    }, "Refreshing content caches…");
    await loadCatalogTab();
  }

  async function apiDownloadZip(path, payload) {
    const response = await fetch(`${apiBase()}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const text = await response.text();
      let message = text.slice(0, 300);
      try {
        const body = JSON.parse(text);
        message = body.error || message;
      } catch {
        /* ignore */
      }
      throw new Error(message || `HTTP ${response.status}`);
    }
    const blob = await response.blob();
    const cd = response.headers.get("Content-Disposition") || "";
    const match = /filename="([^"]+)"/.exec(cd);
    return { blob, filename: match ? match[1] : "bundle-export.zip" };
  }

  function triggerDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  function showExportChoiceDialog() {
    return new Promise((resolve) => {
      const dialog = document.getElementById("bundles-export-dialog");
      const form = document.getElementById("bundles-export-form");
      const messageEl = document.getElementById("bundles-export-dialog-message");
      const cancelBtn = document.getElementById("bundles-export-cancel");
      const saveBtn = document.getElementById("bundles-export-save-first");
      if (!dialog || !form) {
        resolve("current");
        return;
      }
      const dirty = isBasketDirty();
      const hasPreset = Boolean(bundleUiState.loadedPreset?.id);
      if (!dirty) {
        resolve("current");
        return;
      }
      messageEl.textContent = hasPreset
        ? "The basket has unsaved changes compared to the last save or load. Export the current basket, update the saved preset first, or cancel."
        : "The basket has unsaved changes. Export the current basket or cancel.";
      saveBtn.classList.toggle("hidden", !hasPreset);
      const onCancel = () => {
        dialog.close();
        resolve("cancel");
      };
      const onClose = () => {
        cancelBtn?.removeEventListener("click", onCancel);
        form.removeEventListener("submit", onSubmit);
        dialog.removeEventListener("close", onClose);
      };
      const onSubmit = (event) => {
        event.preventDefault();
        const choice = event.submitter?.value === "save" ? "save" : "current";
        dialog.close(choice);
      };
      cancelBtn?.addEventListener("click", onCancel);
      form.addEventListener("submit", onSubmit);
      dialog.addEventListener(
        "close",
        () => {
          onClose();
          const rv = dialog.returnValue || "";
          resolve(rv === "save" ? "save" : rv === "current" ? "current" : "cancel");
        },
        { once: true },
      );
      dialog.showModal();
    });
  }

  async function runExport() {
    const source = activeProfile();
    if (!source || !cptkBundleBasket.items.length) {
      alert("Source profile and at least one basket item required.");
      return;
    }
    const choice = await showExportChoiceDialog();
    if (choice === "cancel") return;
    if (choice === "save") await saveCurrentBundle();
    const bundleName = document.getElementById("bundles-id")?.value?.trim() || undefined;
    const payload = {
      source_profile: source,
      items: basketItemsForApi(),
      bundle_name: bundleName,
    };
    await withLoader(
      () => api("/api/bundles/export/preview", { method: "POST", body: JSON.stringify(payload) }),
      "Planning export…",
    );
    const { blob, filename } = await withLoader(
      () => apiDownloadZip("/api/bundles/export", payload),
      "Building ZIP…",
    );
    triggerDownload(blob, filename);
    if (typeof showActionSuccess === "function") {
      showActionSuccess(`Downloaded ${filename}.`, { title: "Export complete" });
    }
  }

  document.getElementById("bundles-clear")?.addEventListener("click", () => clearBasket());
  document.getElementById("bundles-new")?.addEventListener("click", () => clearBasket({ newBasket: true }));
  document.getElementById("bundles-save")?.addEventListener("click", () => void saveCurrentBundle());
  document.getElementById("bundles-load")?.addEventListener("click", () => void loadSelectedBundle());
  document.getElementById("bundles-delete")?.addEventListener("click", async () => {
    const bundleId = document.getElementById("bundles-preset")?.value;
    const source = activeProfile();
    if (!bundleId || !source) return;
    const proceed = await showConfirmDialog({
      title: "Delete saved bundle",
      message: "Remove this saved bundle preset from local storage?",
      proceedLabel: "Delete",
    });
    if (!proceed) return;
    await api(`/api/bundles/${encodeURIComponent(bundleId)}?profile=${encodeURIComponent(source)}`, {
      method: "DELETE",
    });
    if (bundleUiState.loadedPreset?.id === bundleId) bundleUiState.loadedPreset = null;
    await refreshSavedBundles();
  });

  document.getElementById("bundles-copy")?.addEventListener("click", async () => {
    const source = activeProfile();
    const target = document.getElementById("bundles-copy-target")?.value || "";
    if (!source || !target || !cptkBundleBasket.items.length) {
      alert("Source, target, and basket items required.");
      return;
    }
    const payload = {
      source_profile: source,
      target_profile: target,
      items: basketItemsForApi(),
      shallow_playbooks: true,
    };
    if (typeof mergeCopyPayload === "function") {
      Object.assign(payload, readCopyModeFromRow("bundles"));
    }
    const plan = await withLoader(
      () => api("/api/bundles/copy/preview", { method: "POST", body: JSON.stringify(payload) }),
      "Planning bundle copy…",
    );
    const proceed =
      typeof confirmOperation === "function"
        ? await confirmOperation({
            title: "Confirm bundle copy",
            plan,
            proceedLabel: "Copy bundle",
            itemLabel: "asset",
          })
        : window.confirm("Copy bundle?");
    if (!proceed) return;
    const copyBtn = document.getElementById("bundles-copy");
    const bundleCopyProgress =
      typeof createOperationProgress === "function" ? createOperationProgress("Bundle copy") : null;
    const result = bundleCopyProgress?.runCopy
      ? await bundleCopyProgress.runCopy({
          startMessage: `Copying bundle to ${target}…`,
          wsAction: "bundles.copy",
          payload,
          httpCall: () =>
            api("/api/bundles/copy", { method: "POST", body: JSON.stringify(payload) }),
          loaderMessage: "Copying bundle…",
          busyButton: copyBtn,
          busyLabel: "Copying…",
        })
      : await withLoader(
          () => api("/api/bundles/copy", { method: "POST", body: JSON.stringify(payload) }),
          "Copying bundle…",
        );
    const resultBlock = document.getElementById("bundles-copy-result-block");
    if (typeof presentBundleCopyResultView === "function" && resultBlock) {
      presentBundleCopyResultView(resultBlock, result);
    } else {
      const out = document.getElementById("bundles-action-result");
      if (out) {
        out.textContent = JSON.stringify(result, null, 2);
        out.classList.remove("hidden");
      }
    }
    if (typeof showOutcomeDialog === "function" && typeof summarizeBundleCopyResult === "function") {
      showOutcomeDialog(summarizeBundleCopyResult(result));
    }
  });

  document.getElementById("bundles-export")?.addEventListener("click", () => void runExport());
  document.getElementById("bundles-deps-scan")?.addEventListener("click", () => void scanPlaybookDependencies());
  document.getElementById("bundles-deps-add")?.addEventListener("click", addSelectedDependencies);
  document.getElementById("bundles-refresh-all")?.addEventListener("click", () => void refreshAllCaches());
  document.getElementById("bundles-catalog-add")?.addEventListener("click", addCatalogSelectionToBasket);

  initCatalogGrid();
  if (typeof bindGridSelectionToolbar === "function") {
    bindGridSelectionToolbar({
      table: bundleUiState.catalogTable,
      search: bundleUiState.catalogSearch,
      visibleBtnId: "bundles-catalog-select-visible",
      allBtnId: "bundles-catalog-select-all",
      noneBtnId: "bundles-catalog-select-none",
      onSelectionChange: updateCatalogSelectionCount,
    });
  }
  bindCatalogTabs();
  markBasketClean();

  return {
    loadForActiveProfile: async () => {
      await loadCapabilities();
      await refreshSavedBundles();
      await loadCatalogTab();
    },
  };
}

let bundlesTools = null;
document.addEventListener("DOMContentLoaded", () => {
  bundlesTools = initBundlesSection();
  renderBundleSummary();
  const copyRow = document.getElementById("bundles-copy-row");
  if (copyRow && typeof appendCopyModeControls === "function") {
    appendCopyModeControls(copyRow, "bundles");
  }
});
