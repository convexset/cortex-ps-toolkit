/** Prominent copy / deep-copy alerts with optional collapsible JSON. */

function formatDiffPathSample(diff) {
  const paths = diff?.sample_paths || diff?.differences || [];
  const fromRows = Array.isArray(paths) && paths.length && typeof paths[0] === "object"
    ? paths.map((row) => row.path).filter(Boolean)
    : paths.filter(Boolean);
  const list = fromRows.slice(0, 3);
  if (!list.length) {
    return "";
  }
  const total = diff.difference_count ?? (diff.differences || []).length;
  const suffix = total > 3 ? ", …" : "";
  return ` (${list.join(", ")}${suffix})`;
}

function formatPostCopyDiffTelemetry(row, diff) {
  if (!diff) {
    return "";
  }
  const parts = [];
  parts.push(`probe=${diff.probe || "?"}`);
  parts.push(`outcome=${diff.outcome || (diff.error ? "error" : diff.equal ? "match" : "mismatch")}`);
  if (diff.compare_mode) {
    parts.push(`mode=${diff.compare_mode}`);
  }
  if (row?.status) {
    parts.push(`upload=${row.status}`);
  }
  const src = diff.source_entity_id || row?.playbook_id || row?.script_id || row?.id;
  const tgt = diff.target_entity_id || row?.target_playbook_id || row?.target_script_id;
  if (src || tgt) {
    parts.push(`ids=${src || "?"}→${tgt || "?"}`);
  }
  if (diff.source_fingerprint || diff.read_back_fingerprint) {
    parts.push(`fp=${diff.source_fingerprint || "?"}|${diff.read_back_fingerprint || "?"}`);
  }
  if (diff.read_back_name) {
    parts.push(`read_back_name=${diff.read_back_name}`);
  }
  if (diff.error_code) {
    parts.push(`code=${diff.error_code}`);
  }
  if (diff.binding_unresolved_count != null && diff.binding_unresolved_count > 0) {
    parts.push(`binding_unresolved=${diff.binding_unresolved_count}`);
  }
  if (row?.status_code != null) {
    parts.push(`http=${row.status_code}`);
  }
  return parts.join(" ");
}

function describePostCopyDiffDetail(row, diff) {
  if (!diff) {
    return "";
  }
  const lines = [];
  const telem = formatPostCopyDiffTelemetry(row, diff);
  if (telem) {
    lines.push(telem);
  }
  if (diff.error) {
    lines.push(String(diff.error));
  } else if (diff.equal === false) {
    const count = diff.difference_count ?? (diff.differences || []).length;
    lines.push(`${count} normalized difference(s)${formatDiffPathSample(diff)}`);
    if (diff.first_delta && typeof diff.first_delta === "object") {
      const path = diff.first_delta.path || "(root)";
      const src = diff.first_delta.source;
      const copy = diff.first_delta.copy;
      const deltaHint =
        src !== undefined || copy !== undefined
          ? `first_delta@${path} source=${JSON.stringify(src)} copy=${JSON.stringify(copy)}`
          : `first_delta@${path}`;
      lines.push(deltaHint);
    }
  }
  if (diff.telemetry_note) {
    lines.push(String(diff.telemetry_note));
  }
  return lines.join("\n");
}

function collectRowPostCopyDiffAlerts(rows, entityLabel) {
  const alerts = [];
  for (const row of rows || []) {
    const diff = row.post_copy_diff;
    if (!diff) {
      continue;
    }
    const name = row.name || row.script_id || row.playbook_id || row.id || "?";
    const uploadOk = row.status === "copied" || row.status === "updated";
    if (diff.error) {
      alerts.push({
        severity: uploadOk ? "warning" : "error",
        title: uploadOk
          ? `${entityLabel} saved but diff probe errored: ${name}`
          : `${entityLabel} diff error: ${name}`,
        detail: describePostCopyDiffDetail(row, diff),
        telemetry: formatPostCopyDiffTelemetry(row, diff),
      });
    } else if (diff.outcome === "mismatch" || (diff.equal === false && (diff.flagged || []).length)) {
      const flaggedCount = diff.flagged_count ?? (diff.flagged || diff.differences || []).length;
      alerts.push({
        severity: uploadOk ? "warning" : "error",
        title: uploadOk
          ? `${entityLabel} saved; ${flaggedCount} flagged delta(s): ${name}`
          : `${entityLabel} differs after copy: ${name}`,
        detail: describePostCopyDiffDetail(row, diff),
        telemetry: formatPostCopyDiffTelemetry(row, diff),
      });
    } else if (diff.outcome === "match_ignored_delta" || (diff.ignored || []).length) {
      const ignoredCount = diff.ignored_count ?? (diff.ignored || []).length;
      alerts.push({
        severity: "info",
        title: `${entityLabel} OK with ${ignoredCount} ignored delta(s): ${name}`,
        detail: describePostCopyDiffDetail(row, diff),
        telemetry: formatPostCopyDiffTelemetry(row, diff),
      });
    }
  }
  return alerts;
}

function buildCopyRunTelemetryLines(data) {
  const lines = [];
  const telem = data?.telemetry;
  if (telem && typeof telem === "object") {
    lines.push(
      `TELEM run_id=${telem.run_id || "?"} op=${telem.operation || "?"} toolkit=${telem.toolkit_version || "?"}`,
    );
    if (telem.post_copy_diff_enabled) {
      lines.push(
        `TELEM post_copy_diff probe=${telem.post_copy_diff_probe || "?"} mode=${telem.compare_mode || "?"}`,
      );
    }
  }
  if (data?.source_profile && data?.target_profile) {
    lines.push(`TELEM route ${data.source_profile} → ${data.target_profile}`);
  }
  if (data?.root_playbook_id) {
    lines.push(`TELEM root_playbook=${data.root_playbook_name || "?"} (${data.root_playbook_id})`);
  }
  const diffSummary = data?.post_copy_diff_summary;
  if (data?.post_copy_diff && diffSummary) {
    const total = diffSummary.total || diffSummary;
    const matched = total.matched ?? 0;
    const mismatched = total.mismatched ?? 0;
    const errors = total.errors ?? 0;
    const uploadOkIssues = diffSummary.upload_ok_with_diff_issue;
    lines.push(
      `TELEM post_copy_diff totals match=${matched} mismatch=${mismatched} error=${errors}` +
        (uploadOkIssues != null ? ` upload_ok_but_probe_issue=${uploadOkIssues}` : ""),
    );
    if (diffSummary.interpretation) {
      lines.push(`NOTE ${diffSummary.interpretation}`);
    } else if (uploadOkIssues > 0) {
      lines.push(
        "NOTE upload_ok_but_probe_issue>0: assets may be valid on tenant while repr-copy-fidelity probe disagrees.",
      );
    }
  }
  return lines;
}

function collectDeepCopyAlerts(data) {
  const alerts = [];
  if (!data || typeof data !== "object") {
    return alerts;
  }
  const telemLines = buildCopyRunTelemetryLines(data);
  if (telemLines.length) {
    alerts.push({
      severity: "info",
      title: "Run telemetry",
      detail: telemLines.join("\n"),
    });
  }
  if (data.aborted) {
    alerts.push({
      severity: "error",
      title: "Copy aborted",
      detail: data.reason || "No components were copied.",
    });
    return alerts;
  }

  for (const row of data.script_results || []) {
    if (row.status === "failed") {
      alerts.push({
        severity: "error",
        title: `Script failed: ${row.name || row.script_id || "?"}`,
        detail: row.error || row.message || "See full JSON for details.",
      });
    }
  }
  for (const row of data.playbook_results || []) {
    if (row.status === "failed") {
      alerts.push({
        severity: "error",
        title: `Playbook failed: ${row.name || row.playbook_id || "?"}`,
        detail: row.error || row.message || "See full JSON for details.",
      });
    }
  }
  for (const issue of data.binding_issues || []) {
    const task = issue.task_id ? ` (task ${issue.task_id})` : "";
    alerts.push({
      severity: "warning",
      title: `Binding issue: ${issue.playbook_name || issue.playbook || "?"}${task}`,
      detail: issue.error || issue.binding || "Unresolved script/playbook binding",
    });
  }

  alerts.push(...collectRowPostCopyDiffAlerts(data.script_results, "Script"));
  alerts.push(...collectRowPostCopyDiffAlerts(data.playbook_results, "Playbook"));
  return alerts;
}

const BUNDLE_PHASE_LABELS = {
  integrations: "Integration",
  scripts: "Script",
  playbooks: "Playbook",
  lists: "List",
  design: "Object setup",
};

function bundlePhaseResultRows(phaseKey, phaseResult) {
  if (!phaseResult || typeof phaseResult !== "object") {
    return [];
  }
  const label = BUNDLE_PHASE_LABELS[phaseKey] || phaseKey;
  if (phaseKey === "design" && phaseResult.assets) {
    const rows = [];
    for (const [asset, assetResult] of Object.entries(phaseResult.assets)) {
      const assetLabel = asset.replace(/-/g, " ");
      for (const row of assetResult?.results || []) {
        rows.push({ entityLabel: assetLabel, row });
      }
    }
    return rows;
  }
  return (phaseResult.results || []).map((row) => ({ entityLabel: label, row }));
}

function collectBundleCopyAlerts(data) {
  const alerts = [];
  if (!data || typeof data !== "object") {
    return alerts;
  }
  const telemLines = buildCopyRunTelemetryLines(data);
  if (data.source_profile && data.target_profile) {
    telemLines.unshift(`TELEM operation=${data.operation || "bundles.copy"}`);
  }
  if (telemLines.length) {
    alerts.push({
      severity: "info",
      title: "Run telemetry",
      detail: telemLines.join("\n"),
    });
  }
  if (data.aborted) {
    alerts.push({
      severity: "error",
      title: "Bundle copy aborted",
      detail: data.reason || "No assets were copied.",
    });
    return alerts;
  }

  const phases = data.results || {};
  for (const [phaseKey, phaseResult] of Object.entries(phases)) {
    if (!phaseResult || typeof phaseResult !== "object") {
      continue;
    }
    const phaseLabel = BUNDLE_PHASE_LABELS[phaseKey] || phaseKey;
    if (phaseResult.aborted) {
      alerts.push({
        severity: "error",
        title: `${phaseLabel} phase aborted`,
        detail: phaseResult.reason || "See full JSON for details.",
      });
    }
    if (phaseKey === "design" && phaseResult.halted && phaseResult.halt_reason) {
      alerts.push({
        severity: "warning",
        title: "Object setup halted",
        detail: String(phaseResult.halt_reason),
      });
    }
    if (phaseKey === "playbooks") {
      for (const binding of phaseResult.binding_table || []) {
        const task = binding.task_id ? ` (task ${binding.task_id})` : "";
        alerts.push({
          severity: "warning",
          title: `Unresolved binding: ${binding.playbook_name || binding.playbook_id || "?"}${task}`,
          detail: binding.error || binding.kind || "Binding may fail at runtime until dependencies exist.",
        });
      }
    }
    const wrapped = bundlePhaseResultRows(phaseKey, phaseResult);
    const byLabel = new Map();
    for (const { entityLabel, row } of wrapped) {
      if (!byLabel.has(entityLabel)) {
        byLabel.set(entityLabel, []);
      }
      byLabel.get(entityLabel).push(row);
    }
    for (const [entityLabel, rows] of byLabel) {
      for (const row of rows) {
        if (row.status === "failed") {
          alerts.push({
            severity: "error",
            title: `${entityLabel} failed: ${row.name || row.id || "?"}`,
            detail: row.error || row.message || "See full JSON for details.",
          });
        }
      }
      alerts.push(...collectRowPostCopyDiffAlerts(rows, entityLabel));
    }
  }
  return alerts;
}

/** Mirror design_content.copy_progress.copy_entry_succeeded (lists/scripts use string statuses). */
function copyEntrySucceeded(entry) {
  if (!entry || typeof entry !== "object") {
    return false;
  }
  const status = entry.status;
  const action = entry.action;
  const skipActions = new Set([
    "skip",
    "skipped",
    "missing",
    "conflict",
    "blocked_pack",
    "blocked_non_copyable",
    "incompatible",
  ]);
  const skipStatuses = new Set(["skipped", "conflict", "missing", "failed"]);
  if (skipStatuses.has(status) || skipActions.has(action)) {
    return false;
  }
  if (typeof status === "number") {
    return status >= 200 && status < 300;
  }
  if (status === "copied" || status === "updated") {
    return true;
  }
  if (action === "copy" || action === "update") {
    return true;
  }
  return false;
}

function countCopyStatusRows(rows) {
  const counts = { copied: 0, updated: 0, skipped: 0, failed: 0, other: 0 };
  for (const row of rows || []) {
    const status = row.status;
    if (copyEntrySucceeded(row)) {
      if (row.action === "update" || status === "updated") {
        counts.updated += 1;
      } else {
        counts.copied += 1;
      }
      continue;
    }
    if (status === "skipped" || row.action === "skip") {
      counts.skipped += 1;
    } else if (status === "failed" || (typeof status === "number" && status >= 400)) {
      counts.failed += 1;
    } else if (status != null && status !== "") {
      counts.other += 1;
    }
  }
  return counts;
}

function formatBundlePhaseStatusLine(label, rows) {
  if (!rows?.length) {
    return null;
  }
  const counts = countCopyStatusRows(rows);
  const saved = counts.copied + counts.updated;
  const parts = [];
  if (counts.copied) {
    parts.push(`${counts.copied} copied`);
  }
  if (counts.updated) {
    parts.push(`${counts.updated} updated`);
  }
  if (counts.skipped) {
    parts.push(`${counts.skipped} skipped`);
  }
  if (counts.failed) {
    parts.push(`${counts.failed} failed`);
  }
  const detail = parts.length ? parts.join(", ") : `${rows.length} item(s)`;
  return `${label}: ${saved}/${rows.length} saved (${detail})`;
}

function renderBundleCopyResultSummary(host, data) {
  if (!host || !data) {
    return;
  }
  const lines = [];
  if (typeof buildCopyRunTelemetryLines === "function") {
    const telem = buildCopyRunTelemetryLines(data);
    if (telem.length) {
      lines.push(...telem, "");
    }
  }
  host.classList.remove("copy-result-summary-issues");
  if (data.aborted) {
    lines.push(`Bundle copy aborted: ${data.reason || "no assets copied"}`);
    host.textContent = lines.join("\n");
    host.classList.add("copy-result-summary-issues");
    host.classList.remove("hidden");
    return;
  }

  const phases = data.results || {};
  const phaseOrder = ["integrations", "scripts", "playbooks", "lists", "design"];
  for (const phaseKey of phaseOrder) {
    const phaseResult = phases[phaseKey];
    if (!phaseResult) {
      continue;
    }
    if (phaseKey === "design") {
      if (phaseResult.assets) {
        for (const [asset, assetResult] of Object.entries(phaseResult.assets)) {
          const label = asset.replace(/-/g, " ");
          const line = formatBundlePhaseStatusLine(label, assetResult?.results);
          if (line) {
            lines.push(line);
          }
        }
      }
      if (phaseResult.halted) {
        lines.push(`Object setup: halted — ${phaseResult.halt_reason || "see JSON"}`);
      } else if (phaseResult.executed === false && phaseResult.halt_reason) {
        lines.push(`Object setup: ${phaseResult.halt_reason}`);
      }
      continue;
    }
    const label = BUNDLE_PHASE_LABELS[phaseKey] || phaseKey;
    const line = formatBundlePhaseStatusLine(label, phaseResult.results);
    if (line) {
      lines.push(line);
    }
    if (phaseKey === "playbooks") {
      const bindings = phaseResult.binding_table || [];
      if (bindings.length) {
        lines.push(`Playbook bindings: ${bindings.length} unresolved (see alerts)`);
      } else if ((phaseResult.results || []).length) {
        lines.push("Playbook bindings: no unresolved bindings in shallow plan.");
      }
    }
    if (phaseResult.post_copy_diff_summary && typeof appendPostCopyDiffSummaryLines === "function") {
      appendPostCopyDiffSummaryLines(lines, phaseResult.results, label);
    }
  }

  const hasFailures =
    typeof collectBundleCopyAlerts === "function" &&
    collectBundleCopyAlerts(data).some((alert) => alert.severity === "error");
  const hasWarnings =
    typeof collectBundleCopyAlerts === "function" &&
    collectBundleCopyAlerts(data).some((alert) => alert.severity === "warning");
  host.textContent = lines.join("\n");
  if (hasFailures || hasWarnings) {
    host.classList.add("copy-result-summary-issues");
  }
  host.classList.remove("hidden");
}

function summarizeBundleCopyResult(data) {
  const alerts = typeof collectBundleCopyAlerts === "function" ? collectBundleCopyAlerts(data) : [];
  if (data.aborted) {
    return {
      success: false,
      title: "Bundle copy aborted",
      message: data.reason || "No assets were copied.",
      alerts,
    };
  }
  const phases = data.results || {};
  let failed = 0;
  let saved = 0;
  const parts = [];
  for (const [phaseKey, phaseResult] of Object.entries(phases)) {
    if (!phaseResult || typeof phaseResult !== "object") {
      continue;
    }
    if (phaseResult.aborted) {
      failed += 1;
      parts.push(`${BUNDLE_PHASE_LABELS[phaseKey] || phaseKey} aborted`);
      continue;
    }
    const rows = bundlePhaseResultRows(phaseKey, phaseResult).map((entry) => entry.row);
    const counts = countCopyStatusRows(rows);
    failed += counts.failed;
    saved += counts.copied + counts.updated;
    if (rows.length) {
      parts.push(`${BUNDLE_PHASE_LABELS[phaseKey] || phaseKey}: ${counts.copied + counts.updated}/${rows.length}`);
    }
    if (phaseKey === "design" && phaseResult.halted) {
      failed += 1;
      parts.push("object setup halted");
    }
  }
  let message = parts.length ? parts.join("; ") + "." : "Bundle copy finished.";
  if (data.post_copy_diff) {
    message += " Post-copy diff enabled for scripts, playbooks, and lists.";
  }
  if (typeof buildCopyRunTelemetryLines === "function") {
    const telem = buildCopyRunTelemetryLines(data);
    if (telem.length) {
      message = `${telem.join("\n")}\n\n${message}`;
    }
  }
  const uploadFailed = failed > 0;
  let title = "Bundle copy complete";
  if (uploadFailed) {
    title = "Bundle copy completed with errors";
  } else if (alerts.some((row) => row.severity === "warning")) {
    title = "Bundle copy complete (review warnings)";
  }
  return {
    success: !uploadFailed,
    title,
    message,
    alerts,
  };
}

function presentBundleCopyResultView(container, data) {
  if (!container) {
    return [];
  }
  container.classList.remove("hidden");
  const alertsHost = container.querySelector(".copy-result-alerts") || container.querySelector("#bundles-copy-alerts");
  const summaryHost =
    container.querySelector(".analysis-copy-result-summary") ||
    container.querySelector("#bundles-copy-result-summary");
  const rawDetails = container.querySelector("details.copy-result-raw");
  const pre =
    container.querySelector("#bundles-action-result") ||
    container.querySelector(".analysis-copy-components-result");

  const alerts = collectBundleCopyAlerts(data);
  renderCopyAlertsHost(alertsHost, alerts);
  if (summaryHost) {
    renderBundleCopyResultSummary(summaryHost, data);
  }
  if (pre) {
    pre.textContent = JSON.stringify(data, null, 2);
    pre.classList.remove("hidden");
  }
  if (rawDetails) {
    rawDetails.open = alerts.some((row) => row.severity === "error" || row.severity === "warning");
  }
  if (typeof ensureCopyDiffPanelButton === "function") {
    ensureCopyDiffPanelButton(container, data);
  }
  if (alerts.length) {
    (alertsHost || container).scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  return alerts;
}

function collectBulkCopyAlerts(data, itemLabel = "Item") {
  const alerts = [];
  if (!data || typeof data !== "object") {
    return alerts;
  }
  const telemLines = buildCopyRunTelemetryLines(data);
  if (telemLines.length) {
    alerts.push({
      severity: "info",
      title: "Run telemetry",
      detail: telemLines.join("\n"),
    });
  }
  if (data.aborted) {
    alerts.push({
      severity: "error",
      title: "Copy aborted",
      detail: data.reason || "No items were copied.",
    });
    return alerts;
  }
  const label = itemLabel.charAt(0).toUpperCase() + itemLabel.slice(1);
  for (const row of data.results || []) {
    if (row.status === "failed") {
      alerts.push({
        severity: "error",
        title: `${label} failed: ${row.name || row.id || "?"}`,
        detail: row.error || row.message || "See full JSON for details.",
      });
    }
    alerts.push(...collectRowPostCopyDiffAlerts([row], label));
  }
  return alerts;
}

function renderCopyAlertsHtml(alerts, { maxVisible = 10 } = {}) {
  if (!alerts?.length) {
    return "";
  }
  const visible = alerts.slice(0, maxVisible);
  const extra = alerts.length - visible.length;
  const items = visible
    .map((alert) => {
      let level = alert.severity === "warning" ? "warning" : "error";
      if (alert.severity === "info") {
        level = "info";
      }
      const hasDetail = Boolean(alert.detail);
      const detail = hasDetail
        ? `<pre class="copy-result-alert-detail">${escapeHtml(String(alert.detail))}</pre>`
        : "";
      if (!hasDetail) {
        return (
          `<div class="copy-result-alert copy-result-alert-${level}">` +
          `<strong class="copy-result-alert-title">${escapeHtml(String(alert.title))}</strong>` +
          `</div>`
        );
      }
      return (
        `<details class="copy-result-alert copy-result-alert-${level}">` +
        `<summary class="copy-result-alert-title">${escapeHtml(String(alert.title))}</summary>` +
        detail +
        `</details>`
      );
    })
    .join("");
  const more =
    extra > 0
      ? `<p class="copy-result-alert-more">${extra} more issue(s) — expand full JSON below.</p>`
      : "";
  return `<div class="copy-result-alerts-inner">${items}${more}</div>`;
}

function renderCopyAlertsHost(host, alerts) {
  if (!host) {
    return;
  }
  const actionable = (alerts || []).filter((row) => row.severity !== "info");
  if (!actionable.length && !(alerts || []).length) {
    host.innerHTML = "";
    host.classList.add("hidden");
    return;
  }
  host.innerHTML = renderCopyAlertsHtml(alerts);
  host.classList.remove("hidden");
}

function copyResultChromeFromPre(resultEl) {
  const block = resultEl.closest(".copy-result-block");
  if (!block) {
    return null;
  }
  return {
    block,
    alertsHost: block.querySelector(".copy-result-alerts") || null,
    rawDetails: resultEl.closest("details.copy-result-raw") || null,
    pre: resultEl,
  };
}

function ensureCopyResultChrome(resultEl) {
  if (!resultEl) {
    return { block: null, alertsHost: null, rawDetails: null, pre: null };
  }
  const existing = copyResultChromeFromPre(resultEl);
  if (existing || resultEl.dataset.copyChrome === "1") {
    if (existing) {
      resultEl.dataset.copyChrome = "1";
    }
    return (
      existing || {
        block: null,
        alertsHost: null,
        rawDetails: resultEl.closest("details.copy-result-raw") || null,
        pre: resultEl,
      }
    );
  }

  const parent = resultEl.parentNode;
  if (!parent) {
    return { block: null, alertsHost: null, rawDetails: null, pre: resultEl };
  }

  const block = document.createElement("div");
  block.className = "copy-result-block";
  const alertsHost = document.createElement("div");
  alertsHost.className = "copy-result-alerts hidden";
  alertsHost.setAttribute("aria-live", "assertive");
  const rawDetails = document.createElement("details");
  rawDetails.className = "copy-result-raw";
  const summary = document.createElement("summary");
  summary.textContent = "Full response (JSON)";
  rawDetails.appendChild(summary);

  parent.insertBefore(block, resultEl);
  block.appendChild(alertsHost);
  rawDetails.appendChild(resultEl);
  block.appendChild(rawDetails);
  resultEl.dataset.copyChrome = "1";

  return { block, alertsHost, rawDetails, pre: resultEl };
}

function presentCopyResultView({ resultEl, blockEl, alertsEl, rawDetailsEl, data, collectAlerts, itemLabel }) {
  const chrome = blockEl
    ? {
        block: blockEl,
        alertsHost: alertsEl || blockEl.querySelector(".copy-result-alerts"),
        rawDetails: rawDetailsEl || blockEl.querySelector("details.copy-result-raw"),
        pre: resultEl,
      }
    : ensureCopyResultChrome(resultEl);

  const { block, alertsHost, rawDetails, pre } = chrome;
  const alerts =
    typeof collectAlerts === "function"
      ? collectAlerts(data, itemLabel)
      : collectDeepCopyAlerts(data);

  if (block) {
    block.classList.remove("hidden");
  }
  renderCopyAlertsHost(alertsHost, alerts);
  if (pre) {
    pre.textContent = JSON.stringify(data, null, 2);
    pre.classList.remove("hidden");
  }
  if (rawDetails) {
    const hasErrors = alerts.some((row) => row.severity === "error" || row.severity === "warning");
    rawDetails.open = hasErrors;
  }
  if (typeof ensureCopyDiffPanelButton === "function") {
    ensureCopyDiffPanelButton(block || alertsHost?.parentElement, data);
  }
  if (alerts.length) {
    (alertsHost || block)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  return alerts;
}

function presentDeepCopyResultView(container, data) {
  if (!container) {
    return [];
  }
  container.classList.remove("hidden");
  const alertsHost = container.querySelector(".copy-result-alerts");
  const summaryHost = container.querySelector(".analysis-copy-result-summary");
  const rawDetails = container.querySelector("details.copy-result-raw");
  const pre = container.querySelector(".analysis-copy-components-result");

  const alerts = collectDeepCopyAlerts(data);
  renderCopyAlertsHost(alertsHost, alerts);
  if (typeof renderCopyResultSummary === "function" && summaryHost) {
    renderCopyResultSummary(summaryHost, data);
  }
  if (pre) {
    pre.textContent = JSON.stringify(data, null, 2);
    pre.classList.remove("hidden");
  }
  if (rawDetails) {
    rawDetails.open = alerts.some((row) => row.severity === "error" || row.severity === "warning");
  }
  if (typeof ensureCopyDiffPanelButton === "function") {
    ensureCopyDiffPanelButton(container, data);
  }
  if (alerts.length) {
    (alertsHost || container).scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  return alerts;
}

window.formatDiffPathSample = formatDiffPathSample;
window.formatPostCopyDiffTelemetry = formatPostCopyDiffTelemetry;
window.describePostCopyDiffDetail = describePostCopyDiffDetail;
window.buildCopyRunTelemetryLines = buildCopyRunTelemetryLines;
window.collectDeepCopyAlerts = collectDeepCopyAlerts;
window.collectBundleCopyAlerts = collectBundleCopyAlerts;
window.collectBulkCopyAlerts = collectBulkCopyAlerts;
window.renderBundleCopyResultSummary = renderBundleCopyResultSummary;
window.summarizeBundleCopyResult = summarizeBundleCopyResult;
window.renderCopyAlertsHtml = renderCopyAlertsHtml;
window.presentCopyResultView = presentCopyResultView;
window.presentDeepCopyResultView = presentDeepCopyResultView;
window.presentBundleCopyResultView = presentBundleCopyResultView;
