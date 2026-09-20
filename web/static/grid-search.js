/** Multi-term search for Tabulator grids (name + id), with persistent selection across filters. */

function parseSearchTerms(text) {
  return String(text || "")
    .split(/\s+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function rowMatchesSearch(rowData, terms, { idField = "id", nameField = "name" } = {}) {
  if (!terms.length) {
    return true;
  }
  const id = String(rowData[idField] || "").toLowerCase();
  const name = String(rowData[nameField] || "").toLowerCase();
  return terms.every((term) => {
    const needle = term.toLowerCase();
    return id.includes(needle) || name.includes(needle);
  });
}

function attachGridSearch(table, inputEl, options = {}) {
  const {
    idField = "id",
    nameField = "name",
    selectable = true,
    onSelectionChange,
  } = options;

  const selectedIds = new Set();
  let restoringSelection = false;

  function notify() {
    if (typeof onSelectionChange === "function") {
      onSelectionChange(selectedIds.size, selectedIds);
    }
  }

  function applySearch() {
    if (!table || !inputEl) return;
    const terms = parseSearchTerms(inputEl.value);
    if (!terms.length) {
      table.clearFilter(true);
    } else {
      table.setFilter((data) => rowMatchesSearch(data, terms, { idField, nameField }));
    }
    if (selectable) {
      restoreSelection();
    }
  }

  function restoreSelection() {
    if (!table || !selectable) return;
    restoringSelection = true;
    try {
      // "active" = rows passing the current filter (not viewport-only "visible")
      table.getRows("active").forEach((row) => {
        const id = String(row.getData()[idField] || "");
        if (selectedIds.has(id)) {
          row.select();
        } else {
          row.deselect();
        }
      });
    } finally {
      restoringSelection = false;
    }
    notify();
  }

  function clearSelection() {
    selectedIds.clear();
    if (table) {
      restoringSelection = true;
      try {
        table.deselectRow("all");
      } finally {
        restoringSelection = false;
      }
    }
    notify();
  }

  function selectAllVisible() {
    if (!table) return;
    restoringSelection = true;
    try {
      table.getRows("active").forEach((row) => {
        const id = String(row.getData()[idField] || "");
        selectedIds.add(id);
        row.select();
      });
    } finally {
      restoringSelection = false;
    }
    notify();
  }

  function selectAll() {
    if (!table) return;
    table.getData().forEach((rowData) => {
      selectedIds.add(String(rowData[idField] || ""));
    });
    restoreSelection();
  }

  function getSelectedData() {
    if (!table) return [];
    if (!selectable) return [];
    const ids = selectedIds;
    return table.getData().filter((row) => ids.has(String(row[idField] || "")));
  }

  if (selectable && table) {
    table.on("rowSelected", (row) => {
      if (restoringSelection) return;
      selectedIds.add(String(row.getData()[idField] || ""));
      notify();
    });
    table.on("rowDeselected", (row) => {
      if (restoringSelection) return;
      selectedIds.delete(String(row.getData()[idField] || ""));
      notify();
    });
  }

  if (inputEl) {
    inputEl.addEventListener("input", applySearch);
  }

  return {
    applySearch,
    clearSelection,
    selectAllVisible,
    selectAll,
    getSelectedData,
    getSelectedIds: () => [...selectedIds],
    restoreSelection,
    parseSearchTerms: () => parseSearchTerms(inputEl?.value),
  };
}

window.parseSearchTerms = parseSearchTerms;
window.rowMatchesSearch = rowMatchesSearch;
window.attachGridSearch = attachGridSearch;
