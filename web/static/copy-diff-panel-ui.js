/** Modal panel: classified post-copy diffs (flagged vs ignored) for any copy response. */

const COPY_DIFF_VALUE_TRUNCATE = 160;

function copyDiffRowFromEntry(row, namePrefix = "") {
  const diff = row?.post_copy_diff;
  if (!diff) {
    return null;
  }
  const baseName =
    row.name ||
    row.target_name ||
    row.list_id ||
    row.playbook_id ||
    row.script_id ||
    row.id ||
    "?";
  return {
    name: namePrefix ? `${namePrefix}: ${baseName}` : baseName,
    status: row.status,
    kind: diff.kind,
    outcome: diff.outcome,
    diff,
  };
}

function extractCopyDiffRowsFromList(entries, namePrefix = "") {
  const rows = [];
  for (const row of entries || []) {
    const mapped = copyDiffRowFromEntry(row, namePrefix);
    if (mapped) {
      rows.push(mapped);
    }
  }
  return rows;
}

function extractCopyDiffRowsFromPhaseContainer(phaseResult, phaseLabel = "") {
  if (!phaseResult || typeof phaseResult !== "object") {
    return [];
  }
  const rows = [];
  if (phaseResult.copy_diff_report?.rows?.length) {
    for (const row of phaseResult.copy_diff_report.rows) {
      rows.push({
        name: phaseLabel ? `${phaseLabel}: ${row.name || "?"}` : row.name || "?",
        status: row.status,
        kind: row.kind || row.post_copy_diff?.kind,
        outcome: row.outcome || row.post_copy_diff?.outcome,
        diff: row.post_copy_diff || {},
      });
    }
  }
  rows.push(...extractCopyDiffRowsFromList(phaseResult.results, phaseLabel));
  const assets = phaseResult.assets;
  if (assets && typeof assets === "object") {
    for (const [asset, assetResult] of Object.entries(assets)) {
      const label = phaseLabel ? `${phaseLabel}/${asset}` : asset;
      rows.push(...extractCopyDiffRowsFromPhaseContainer(assetResult, label));
    }
  }
  return rows;
}

function extractCopyDiffRows(data) {
  if (!data || typeof data !== "object") {
    return [];
  }
  if (data.copy_diff_report?.rows?.length) {
    return data.copy_diff_report.rows.map((row) => ({
      name: row.name || "?",
      status: row.status,
      kind: row.kind || row.post_copy_diff?.kind,
      outcome: row.outcome || row.post_copy_diff?.outcome,
      diff: row.post_copy_diff || {},
    }));
  }
  const nestedPhases = data.results;
  if (nestedPhases && typeof nestedPhases === "object" && !Array.isArray(nestedPhases)) {
    const rows = [];
    for (const [phase, phaseResult] of Object.entries(nestedPhases)) {
      rows.push(...extractCopyDiffRowsFromPhaseContainer(phaseResult, phase));
    }
    if (rows.length) {
      return rows;
    }
  }
  const rows = [];
  for (const key of ["results", "script_results", "playbook_results"]) {
    rows.push(...extractCopyDiffRowsFromList(data[key]));
  }
  return rows;
}

function copyResponseHasPostCopyDiff(data) {
  if (!data || typeof data !== "object") {
    return false;
  }
  if (data.post_copy_diff) {
    return true;
  }
  const phases = data.results;
  if (!phases || typeof phases !== "object" || Array.isArray(phases)) {
    return false;
  }
  for (const phaseResult of Object.values(phases)) {
    if (!phaseResult || typeof phaseResult !== "object") {
      continue;
    }
    if (phaseResult.post_copy_diff || phaseResult.copy_diff_report?.rows?.length) {
      return true;
    }
    if (extractCopyDiffRowsFromList(phaseResult.results).length) {
      return true;
    }
  }
  return false;
}

function truncateCopyDiffValue(value, maxLen = COPY_DIFF_VALUE_TRUNCATE) {
  if (value === undefined) {
    return "∅";
  }
  if (value === null) {
    return "null";
  }
  let text;
  if (typeof value === "object") {
    try {
      text = JSON.stringify(value);
    } catch {
      text = String(value);
    }
  } else {
    text = String(value);
  }
  text = text.replace(/\s+/g, " ").trim();
  if (text.length <= maxLen) {
    return text;
  }
  return `${text.slice(0, maxLen)}…`;
}

function deltaSummaryLine(delta) {
  const path = delta.path || "(root)";
  if (delta.source_len != null || delta.copy_len != null) {
    return `${path} · array length ${delta.source_len ?? "?"} → ${delta.copy_len ?? "?"}`;
  }
  const src = truncateCopyDiffValue(delta.source, 48);
  const copy = truncateCopyDiffValue(delta.copy, 48);
  return `${path} · ${src} → ${copy}`;
}

function renderDeltaEntryHtml(delta, classification) {
  const summary = escapeHtml(deltaSummaryLine(delta));
  const reason = delta.ignore_reason
    ? `<p class="copy-diff-delta-reason"><strong>Ignore reason:</strong> ${escapeHtml(delta.ignore_reason)}</p>`
    : "";
  let body = "";
  if (delta.source_len != null || delta.copy_len != null) {
    body =
      `<dl class="copy-diff-delta-values">` +
      `<dt>Source length</dt><dd>${escapeHtml(String(delta.source_len ?? "—"))}</dd>` +
      `<dt>Target length</dt><dd>${escapeHtml(String(delta.copy_len ?? "—"))}</dd>` +
      `</dl>`;
  } else {
    body =
      `<dl class="copy-diff-delta-values">` +
      `<dt>Source (truncated)</dt><dd><code>${escapeHtml(truncateCopyDiffValue(delta.source))}</code></dd>` +
      `<dt>Target (truncated)</dt><dd><code>${escapeHtml(truncateCopyDiffValue(delta.copy))}</code></dd>` +
      `</dl>`;
  }
  return (
    `<details class="copy-diff-delta copy-diff-delta-${classification}">` +
    `<summary class="copy-diff-delta-summary">${summary}</summary>` +
    `<div class="copy-diff-delta-body">${reason}${body}</div>` +
    `</details>`
  );
}

function bucketPathPreview(deltas, max = 3) {
  if (!deltas?.length) {
    return "";
  }
  const paths = deltas
    .slice(0, max)
    .map((d) => d.path || "(root)")
    .join(", ");
  const extra = deltas.length > max ? `, +${deltas.length - max} more` : "";
  return paths + extra;
}

function renderDeltaBucketHtml(label, deltas, classification) {
  const count = deltas.length;
  const preview = bucketPathPreview(deltas);
  const summaryText = preview
    ? `${label} (${count}) — ${preview}`
    : `${label} (${count}) — none`;
  const entries = count
    ? deltas.map((delta) => renderDeltaEntryHtml(delta, classification)).join("")
    : `<p class="copy-diff-bucket-empty">No ${label.toLowerCase()} deltas.</p>`;
  return (
    `<details class="copy-diff-bucket copy-diff-bucket-${classification}">` +
    `<summary class="copy-diff-bucket-summary">${escapeHtml(summaryText)}</summary>` +
    `<div class="copy-diff-bucket-body">${entries}</div>` +
    `</details>`
  );
}

function renderItemSummaryLine(row) {
  const diff = row.diff || {};
  const flagged = diff.flagged || diff.differences || [];
  const ignored = diff.ignored || [];
  const outcome = row.outcome || (diff.equal ? "match" : "mismatch");
  const parts = [
    escapeHtml(row.name),
    `<span class="copy-diff-outcome copy-diff-outcome-${escapeHtml(outcome)}">${escapeHtml(outcome)}</span>`,
    `<span class="copy-diff-item-counts">flagged ${flagged.length} · ignored ${ignored.length}</span>`,
    `<span class="copy-diff-item-meta">${escapeHtml(row.kind || "?")} · ${escapeHtml(String(row.status || "?"))}</span>`,
  ];
  return parts.join(" ");
}

function renderCopyDiffPanelHtml(data) {
  const rows = extractCopyDiffRows(data);
  const report = data?.copy_diff_report || {};
  const probe = report.probe || data?.telemetry?.post_copy_diff_probe || data?.post_copy_diff_summary?.probe || "?";
  const telem = data?.telemetry;
  const header = [
    `<details class="copy-diff-report-header">` +
      `<summary class="copy-diff-lead">` +
      `Report · probe <code>${escapeHtml(String(probe))}</code>` +
      (report.flagged_delta_total != null
        ? ` · flagged Δ ${report.flagged_delta_total} · ignored Δ ${report.ignored_delta_total ?? 0}`
        : "") +
      ` · ${rows.length} item(s)` +
      `</summary>` +
      `<div class="copy-diff-header-body">` +
      (telem?.run_id
        ? `<p class="copy-diff-meta">run_id=${escapeHtml(telem.run_id)} · op=${escapeHtml(telem.operation || "?")} · toolkit=${escapeHtml(telem.toolkit_version || "?")}</p>`
        : "") +
      `<p class="copy-diff-meta">Expand each item for flagged vs ignored field deltas. Expand a field row for truncated source/target values.</p>` +
      `</div>` +
      `</details>`,
  ];
  if (!rows.length) {
    header.push(
      `<p class="copy-diff-empty">No post-copy diff rows. Enable <strong>Diff after copy</strong> on the copy action, then re-run.</p>`,
    );
    return header.join("");
  }

  const sections = rows.map((row) => {
    const diff = row.diff || {};
    const flagged = diff.flagged || diff.differences || [];
    const ignored = diff.ignored || [];
    return (
      `<details class="copy-diff-item">` +
      `<summary class="copy-diff-item-summary">${renderItemSummaryLine(row)}</summary>` +
      `<div class="copy-diff-item-body">` +
      renderDeltaBucketHtml("Flagged", flagged, "flagged") +
      renderDeltaBucketHtml("Ignored", ignored, "ignored") +
      `</div>` +
      `</details>`
    );
  });
  return header.join("") + `<div class="copy-diff-items">${sections.join("")}</div>`;
}

function showCopyDiffPanel(data) {
  const dialog = document.getElementById("copy-diff-dialog");
  const panel = document.getElementById("copy-diff-panel");
  if (!dialog || !panel) {
    window.alert("Copy diff panel is not available in this page.");
    return;
  }
  panel.innerHTML = renderCopyDiffPanelHtml(data);
  dialog.showModal();
}

function ensureCopyDiffPanelButton(container, data) {
  const hasRows = extractCopyDiffRows(data).length > 0;
  if (!container || (!copyResponseHasPostCopyDiff(data) && !hasRows)) {
    return;
  }
  let bar = container.querySelector(".copy-diff-actions");
  if (!bar) {
    bar = document.createElement("div");
    bar.className = "copy-diff-actions";
    const block = container.querySelector(".copy-result-alerts") || container;
    block.insertAdjacentElement("afterend", bar);
  }
  bar.innerHTML =
    `<button type="button" class="action copy-diff-view-btn">View classified copy diffs</button>`;
  bar.querySelector(".copy-diff-view-btn")?.addEventListener("click", () => {
    showCopyDiffPanel(data);
  });
}

window.extractCopyDiffRows = extractCopyDiffRows;
window.showCopyDiffPanel = showCopyDiffPanel;
window.ensureCopyDiffPanelButton = ensureCopyDiffPanelButton;
