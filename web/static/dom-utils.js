/** Shared DOM helpers for Cortex PS Toolkit web UI. */

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function cptkGridHeight(variant = "default") {
  const tokenByVariant = {
    default: "--grid-height",
    compact: "--grid-height-compact",
    nested: "--grid-height-nested",
  };
  const token = tokenByVariant[variant] || tokenByVariant.default;
  const fromCss = getComputedStyle(document.documentElement).getPropertyValue(token).trim();
  if (fromCss) return fromCss;
  const fallback = { default: "420px", compact: "320px", nested: "260px" };
  return fallback[variant] || fallback.default;
}

function bindGridSelectionToolbar({
  table,
  search,
  visibleBtnId,
  allBtnId,
  noneBtnId,
  onSelectionChange,
}) {
  const notify = () => {
    if (typeof onSelectionChange === "function") onSelectionChange();
  };
  const visibleBtn = visibleBtnId ? document.getElementById(visibleBtnId) : null;
  const allBtn = allBtnId ? document.getElementById(allBtnId) : null;
  const noneBtn = noneBtnId ? document.getElementById(noneBtnId) : null;

  visibleBtn?.addEventListener("click", () => {
    if (!table) return;
    if (search) search.selectAllVisible();
    else {
      table.selectRow("active");
      notify();
    }
  });
  allBtn?.addEventListener("click", () => {
    if (!table) return;
    if (search) search.selectAll();
    else {
      table.selectRow("all");
      notify();
    }
  });
  noneBtn?.addEventListener("click", () => {
    if (!table) return;
    if (search) search.clearSelection();
    else table.deselectRow();
    notify();
  });
}

window.escapeHtml = escapeHtml;
window.cptkGridHeight = cptkGridHeight;
window.bindGridSelectionToolbar = bindGridSelectionToolbar;
