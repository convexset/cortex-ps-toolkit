/**
 * Custom XQL visual builder (encoding slots + Plotly render via toolkit API).
 */
(function () {
  const STORAGE_KEY = "xql_monitor_visual_specs_v1";

  function toolkitApi(path, options = {}) {
    return fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    }).then(async (response) => {
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(body.error || response.statusText || "Request failed");
      }
      return body;
    });
  }

  function loadStore() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return { activeId: null, items: [] };
      const parsed = JSON.parse(raw);
      return {
        activeId: parsed.activeId || null,
        items: Array.isArray(parsed.items) ? parsed.items : [],
      };
    } catch {
      return { activeId: null, items: [] };
    }
  }

  function saveStore(store) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  }

  function newId() {
    return `viz_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  }

  function columnTypeLabel(monitorType) {
    if (monitorType === "integer" || monitorType === "number") return "number";
    if (monitorType === "timestamp") return "datetime";
    return "text";
  }

  function slotAcceptsColumn(slot, monitorType) {
    const mapped = columnTypeLabel(monitorType);
    return slot.accepted_types.includes(mapped);
  }

  const builder = {
    chartTypes: [],
    els: {},
    getRows: () => [],
    getColumns: () => [],
    inferColumnType: () => "string",
    useToolkitApi: () => false,
    getProfile: () => "",
    onStatus: () => {},
  };

  function buildSpecFromForm() {
    const chartType = builder.els.chartType.value;
    const chart = builder.chartTypes.find((item) => item.id === chartType);
    const encodings = {};
    if (chart) {
      chart.slots.forEach((slot) => {
        const select = builder.els.encodingFields[slot.id];
        if (!select) return;
        const field = select.value;
        if (!field) {
          encodings[slot.id] = null;
          return;
        }
        encodings[slot.id] = {
          field,
          type: columnTypeLabel(builder.inferColumnType(builder.getRows(), field)),
        };
      });
    }
    return {
      chart_type: chartType,
      label: builder.els.visualLabel.value.trim(),
      title: builder.els.visualTitle.value.trim(),
      encodings,
      display: {
        limit_categories: Number(builder.els.limitCategories.value) || 20,
      },
      query_ref: {},
    };
  }

  function applySpecToForm(spec) {
    builder.els.chartType.value = spec.chart_type || builder.chartTypes[0]?.id || "";
    builder.els.visualLabel.value = spec.label || "";
    builder.els.visualTitle.value = spec.title || "";
    builder.els.limitCategories.value = String(spec.display?.limit_categories ?? 20);
    refreshEncodingFields();
    const enc = spec.encodings || {};
    Object.keys(builder.els.encodingFields).forEach((slotId) => {
      const select = builder.els.encodingFields[slotId];
      const mapping = enc[slotId];
      select.value = mapping?.field || "";
    });
  }

  function refreshEncodingFields() {
    const chart = builder.chartTypes.find((item) => item.id === builder.els.chartType.value);
    const host = builder.els.encodingHost;
    if (!host || !chart) return;
    host.innerHTML = "";
    builder.els.encodingFields = {};
    const rows = builder.getRows();
    const columns = builder.getColumns();
    chart.slots.forEach((slot) => {
      const row = document.createElement("label");
      row.className = "field viz-encoding-row";
      const title = `${slot.label}${slot.required ? " *" : ""}`;
      const select = document.createElement("select");
      select.dataset.slotId = slot.id;
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = slot.required ? "— select column —" : "— not used —";
      select.appendChild(empty);
      columns.forEach((col) => {
        const opt = document.createElement("option");
        opt.value = col;
        const inferred = builder.inferColumnType(rows, col);
        opt.textContent = `${col} (${inferred})`;
        opt.disabled = rows.length > 0 && !slotAcceptsColumn(slot, inferred);
        select.appendChild(opt);
      });
      row.innerHTML = `<span>${title}</span>`;
      row.appendChild(select);
      host.appendChild(row);
      builder.els.encodingFields[slot.id] = select;
    });
  }

  function refreshSavedList() {
    const store = loadStore();
    const select = builder.els.savedSelect;
    if (!select) return;
    select.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = store.items.length ? "— load saved visual —" : "No saved visuals yet";
    select.appendChild(placeholder);
    store.items.forEach((item) => {
      const opt = document.createElement("option");
      opt.value = item.id;
      opt.textContent = item.label || item.id;
      select.appendChild(opt);
    });
    if (store.activeId) {
      select.value = store.activeId;
    }
  }

  async function loadChartTypes() {
    if (builder.useToolkitApi()) {
      const data = await toolkitApi("/api/xql/visualizations/chart-types");
      builder.chartTypes = data.chart_types || [];
    } else {
      builder.chartTypes = [];
    }
    if (!builder.chartTypes.length) {
      builder.chartTypes = [
        {
          id: "stacked_bar_horizontal",
          label: "Horizontal stacked bar",
          enabled: true,
          slots: [
            { id: "category", label: "Category (Y)", required: true, accepted_types: ["text"] },
            { id: "measure", label: "Measure (X)", required: true, accepted_types: ["number"] },
            { id: "stack", label: "Stack / series", required: false, accepted_types: ["text"] },
            { id: "color", label: "Colour", required: false, accepted_types: ["text"] },
          ],
        },
        {
          id: "stacked_bar_vertical",
          label: "Vertical stacked bar",
          enabled: true,
          slots: [
            { id: "category", label: "Category (X)", required: true, accepted_types: ["text"] },
            { id: "measure", label: "Measure (Y)", required: true, accepted_types: ["number"] },
            { id: "stack", label: "Stack / series", required: false, accepted_types: ["text"] },
            { id: "color", label: "Colour", required: false, accepted_types: ["text"] },
          ],
        },
      ];
    }
    builder.els.chartType.innerHTML = "";
    builder.chartTypes.forEach((chart) => {
      const opt = document.createElement("option");
      opt.value = chart.id;
      opt.textContent = chart.enabled ? chart.label : `${chart.label} (soon)`;
      opt.disabled = !chart.enabled;
      builder.els.chartType.appendChild(opt);
    });
    refreshEncodingFields();
  }

  function showValidation(validation) {
    const host = builder.els.validationHost;
    if (!host) return;
    const parts = [];
    if (validation.errors?.length) {
      parts.push(`Errors: ${validation.errors.join(" ")}`);
    }
    if (validation.warnings?.length) {
      parts.push(`Warnings: ${validation.warnings.join(" ")}`);
    }
    if (!parts.length) {
      host.textContent = "Spec looks valid.";
      host.className = "hint ok";
      return;
    }
    host.textContent = parts.join(" ");
    host.className = validation.errors?.length ? "hint error" : "hint";
  }

  async function renderVisual() {
    const rows = builder.getRows();
    if (!rows.length) {
      builder.onStatus("Load query results before rendering a chart.", "error");
      return;
    }
    if (!builder.useToolkitApi()) {
      builder.onStatus("Custom charts require the toolkit dev server (embedded mode).", "error");
      return;
    }
    const spec = buildSpecFromForm();
    builder.onStatus("Rendering chart…", "");
    try {
      const data = await toolkitApi("/api/xql/visualizations/render", {
        method: "POST",
        body: JSON.stringify({ rows, spec }),
      });
      showValidation(data.validation || {});
      if (typeof Plotly === "undefined") {
        throw new Error("Plotly is not loaded");
      }
      builder.els.canvasPanel.classList.remove("hidden");
      Plotly.react(builder.els.plotDiv, data.figure.data, data.figure.layout, {
        responsive: true,
        displaylogo: false,
      });
      builder.onStatus("Chart rendered.", "ok");
    } catch (err) {
      builder.onStatus(err.message || String(err), "error");
    }
  }

  async function validateSpec() {
    const rows = builder.getRows();
    if (!rows.length || !builder.useToolkitApi()) return;
    const spec = buildSpecFromForm();
    const data = await toolkitApi("/api/xql/visualizations/validate", {
      method: "POST",
      body: JSON.stringify({ rows, spec }),
    });
    showValidation(data);
  }

  function saveVisualLocal() {
    const spec = buildSpecFromForm();
    const label = builder.els.visualLabel.value.trim() || spec.title || "Chart";
    const store = loadStore();
    const id = store.activeId || newId();
    const columns = builder.getColumns();
    const record = {
      id,
      label,
      spec,
      columns,
      savedAt: new Date().toISOString(),
    };
    const index = store.items.findIndex((item) => item.id === id);
    if (index >= 0) store.items[index] = record;
    else store.items.push(record);
    store.activeId = id;
    saveStore(store);
    refreshSavedList();
    builder.onStatus(`Saved visual “${label}” locally.`, "ok");
    if (builder.useToolkitApi() && builder.getProfile()) {
      toolkitApi("/api/xql/visualizations", {
        method: "POST",
        body: JSON.stringify({
          id,
          label,
          profile: builder.getProfile(),
          spec,
          columns_fingerprint: columns,
        }),
      }).catch(() => {});
    }
  }

  function loadSavedVisual(id) {
    const store = loadStore();
    const item = store.items.find((row) => row.id === id);
    if (!item) return;
    store.activeId = id;
    saveStore(store);
    applySpecToForm(item.spec);
    builder.els.visualLabel.value = item.label || "";
    builder.onStatus(`Loaded saved visual “${item.label}”.`, "ok");
  }

  function deleteSavedVisual() {
    const id = builder.els.savedSelect.value;
    if (!id) return;
    const store = loadStore();
    store.items = store.items.filter((item) => item.id !== id);
    if (store.activeId === id) store.activeId = null;
    saveStore(store);
    refreshSavedList();
    builder.onStatus("Deleted saved visual.", "ok");
    if (builder.useToolkitApi()) {
      toolkitApi(`/api/xql/visualizations/${encodeURIComponent(id)}`, { method: "DELETE" }).catch(() => {});
    }
  }

  function openBuilder() {
    builder.els.builderPanel.classList.remove("hidden");
    refreshEncodingFields();
    builder.els.builderPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function init(options) {
    Object.assign(builder, options);
    builder.els = {
      builderPanel: document.getElementById("custom-viz-builder"),
      chartType: document.getElementById("custom-viz-chart-type"),
      visualLabel: document.getElementById("custom-viz-label"),
      visualTitle: document.getElementById("custom-viz-title"),
      limitCategories: document.getElementById("custom-viz-limit"),
      encodingHost: document.getElementById("custom-viz-encodings"),
      validationHost: document.getElementById("custom-viz-validation"),
      canvasPanel: document.getElementById("custom-viz-canvas-panel"),
      plotDiv: document.getElementById("custom-viz-plot"),
      savedSelect: document.getElementById("custom-viz-saved"),
      encodingFields: {},
    };
    if (!builder.els.builderPanel) return;

    document.getElementById("custom-viz-open-btn")?.addEventListener("click", openBuilder);
    builder.els.chartType?.addEventListener("change", refreshEncodingFields);
    document.getElementById("custom-viz-render-btn")?.addEventListener("click", () => void renderVisual());
    document.getElementById("custom-viz-validate-btn")?.addEventListener("click", () => void validateSpec());
    document.getElementById("custom-viz-save-btn")?.addEventListener("click", saveVisualLocal);
    builder.els.savedSelect?.addEventListener("change", () => {
      if (builder.els.savedSelect.value) loadSavedVisual(builder.els.savedSelect.value);
    });
    document.getElementById("custom-viz-delete-btn")?.addEventListener("click", deleteSavedVisual);

    void loadChartTypes().then(() => {
      refreshSavedList();
      const store = loadStore();
      if (store.activeId) {
        const item = store.items.find((row) => row.id === store.activeId);
        if (item) applySpecToForm(item.spec);
      }
    });
  }

  function onResultsUpdated() {
    if (!builder.els.builderPanel) return;
    refreshEncodingFields();
  }

  window.XqlVisualBuilder = { init, onResultsUpdated, openBuilder };
})();
