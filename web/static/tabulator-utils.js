/** Shared Tabulator helpers: column header filters and analysis-panel tables. */

const cptkPendingAnalysisTables = new Map();
let cptkAnalysisTableSeq = 0;

function cptkEnhanceColumns(columns, options = {}) {
  const { headerFilter = true } = options;
  if (!headerFilter || !Array.isArray(columns)) {
    return columns;
  }
  return columns.map((col) => {
    if (col.formatter === "rowSelection") {
      return col;
    }
    if (col.headerFilter === false || col.headerSort === false && col.title === "Actions") {
      return col;
    }
    if (typeof col.formatter === "function" && String(col.title || "").toLowerCase() === "actions") {
      return { ...col, headerSort: false, headerFilter: false };
    }
    if (col.formatter === "tickCross") {
      return {
        headerFilter: "tickCross",
        headerFilterPlaceholder: "…",
        ...col,
      };
    }
    return {
      headerFilter: "input",
      headerFilterPlaceholder: "Filter…",
      ...col,
    };
  });
}

const CPTK_ANALYSIS_NUMERIC_HEADERS = new Set([
  "Count",
  "Min from start",
  "Max from start",
  "Min to terminal",
  "Max to terminal",
]);

function buildAnalysisTabulatorConfig(headers, rows) {
  const htmlFields = new Set();
  const data = (rows || []).map((row) => {
    const obj = {};
    headers.forEach((_, index) => {
      const field = `c${index}`;
      const cell = row[index];
      if (cell && typeof cell === "object" && cell.html != null) {
        obj[field] = cell.html;
        htmlFields.add(field);
      } else {
        obj[field] = cell == null || cell === "" ? "—" : String(cell);
      }
    });
    return obj;
  });

  const columns = headers.map((title, index) => {
    const field = `c${index}`;
    const col = {
      title,
      field,
      headerFilter: "input",
      headerFilterPlaceholder: "…",
      minWidth: 72,
    };
    if (htmlFields.has(field)) {
      col.formatter = "html";
    } else if (CPTK_ANALYSIS_NUMERIC_HEADERS.has(title)) {
      col.sorter = "number";
      col.hozAlign = "right";
    } else if (title === "Reachable" || title === "System" || title === "Copyable" || title === "Resolved") {
      col.headerFilter = "list";
      col.headerFilterParams = { values: { "": "All", Yes: "Yes", No: "No" }, clearable: true };
    }
    return col;
  });

  return { columns, data };
}

function registerAnalysisTable(headers, rows, options = {}) {
  const id = options.id || `analysis-table-${++cptkAnalysisTableSeq}`;
  cptkPendingAnalysisTables.set(id, { headers, rows, options });
  return id;
}

function renderAnalysisTableMountHtml(headers, rows, options = {}) {
  const id = registerAnalysisTable(headers, rows, options);
  return `<div class="analysis-table-mount" data-table-id="${id}"></div>`;
}

function mountAnalysisTable(mountEl, config) {
  if (!mountEl || typeof Tabulator !== "function") {
    return null;
  }
  const { headers, rows, options = {} } = config;
  const { columns, data } = buildAnalysisTabulatorConfig(headers, rows);
  const height = options.height || "min(420px, 55vh)";
  mountEl.innerHTML = "";
  mountEl.classList.add("analysis-tabulator-host");
  const table = new Tabulator(mountEl, {
    data,
    columns,
    layout: "fitDataStretch",
    height,
    placeholder: "None",
    initialSort: options.initialSort || [],
  });
  mountEl._tabulator = table;
  return table;
}

function hydrateAnalysisTables(root) {
  if (!root) {
    return;
  }
  root.querySelectorAll(".analysis-table-mount[data-table-id]").forEach((mountEl) => {
    const id = mountEl.dataset.tableId;
    const config = cptkPendingAnalysisTables.get(id);
    if (!config) {
      return;
    }
    if (mountEl._tabulator) {
      mountEl._tabulator.destroy();
      mountEl._tabulator = null;
    }
    mountAnalysisTable(mountEl, config);
  });
}

function clearAnalysisTableRegistry(root) {
  if (!root) {
    cptkPendingAnalysisTables.clear();
    return;
  }
  root.querySelectorAll(".analysis-table-mount[data-table-id]").forEach((mountEl) => {
    const id = mountEl.dataset.tableId;
    if (id) {
      cptkPendingAnalysisTables.delete(id);
    }
    if (mountEl._tabulator) {
      mountEl._tabulator.destroy();
    }
  });
}

window.cptkEnhanceColumns = cptkEnhanceColumns;
window.renderAnalysisTableMountHtml = renderAnalysisTableMountHtml;
window.hydrateAnalysisTables = hydrateAnalysisTables;
window.mountAnalysisTable = mountAnalysisTable;
window.clearAnalysisTableRegistry = clearAnalysisTableRegistry;
