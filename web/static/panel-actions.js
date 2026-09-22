/** Shared confirm/outcome helpers for admin and content panels. */

function formatPreviewEntries(preview, { title = "Preview", itemLabel = "item" } = {}) {
  const entries = Array.isArray(preview?.entries)
    ? preview.entries
    : Array.isArray(preview?.items)
      ? preview.items
      : [];
  const counts = preview?.counts && typeof preview.counts === "object" ? preview.counts : null;
  const lines = [title, ""];

  if (entries.length) {
    const names = entries
      .map((entry) => entry.name || entry.id || entry.key_id || entry.display || "(unnamed)")
      .join(", ");
    lines.push(`${entries.length} ${itemLabel}(s): ${names}`);
  }

  if (counts) {
    lines.push("");
    Object.entries(counts).forEach(([key, value]) => {
      if (value != null && value !== 0) lines.push(`${key}: ${value}`);
    });
  }

  entries.forEach((entry) => {
    if (entry.action) {
      lines.push(`• ${entry.name || entry.id || "(item)"}: ${entry.action}`);
    }
  });

  if (!entries.length && !counts && preview) {
    lines.push(JSON.stringify(preview, null, 2));
  }

  lines.push("", "Proceed?");
  return lines.join("\n");
}

function showActionResult(resultElementId, result) {
  const el = document.getElementById(resultElementId);
  if (!el) return;
  el.textContent = JSON.stringify(result, null, 2);
  el.classList.remove("hidden");
}

function summarizeGenericResult(result, { itemLabel = "item", operation = "generic" } = {}) {
  if (result?.aborted) {
    return {
      success: false,
      title: operation === "copy" ? "Copy aborted" : "Operation aborted",
      message: result.reason || "No changes were made.",
    };
  }
  if (Array.isArray(result?.results) && typeof summarizeBulkCopyResult === "function" && operation === "copy") {
    return summarizeBulkCopyResult(result, itemLabel);
  }
  if (Array.isArray(result?.results) && typeof summarizeBulkDeleteResult === "function" && operation === "delete") {
    return summarizeBulkDeleteResult(result, itemLabel);
  }
  const ok = result?.ok !== false && !result?.error;
  const count = result?.count ?? result?.copied ?? result?.deleted;
  let message = ok ? "Operation completed." : result?.error || "Operation finished with issues.";
  if (count != null) message = `${itemLabel}s processed: ${count}.`;
  return {
    success: ok,
    title: ok ? "Complete" : "Completed with issues",
    message,
  };
}

function showActionOutcome(resultElementId, result, options = {}) {
  showActionResult(resultElementId, result);
  if (typeof showOutcomeDialog !== "function") return;
  const summary = summarizeGenericResult(result, options);
  showOutcomeDialog(summary);
}

function showActionError(message, options = {}) {
  if (typeof showOutcomeDialog === "function") {
    showOutcomeDialog({ title: options.title || "Operation failed", message, success: false });
    return;
  }
  alert(message);
}

function showActionSuccess(message, options = {}) {
  if (typeof showOutcomeDialog === "function") {
    showOutcomeDialog({ title: options.title || "Success", message, success: true });
    return;
  }
  if (window.cptkWs?.showToast) {
    window.cptkWs.showToast({ level: "success", message, autoDismissMs: 3000 });
    return;
  }
  alert(message);
}

window.formatPreviewEntries = formatPreviewEntries;
window.showActionResult = showActionResult;
window.showActionOutcome = showActionOutcome;
window.summarizeGenericResult = summarizeGenericResult;
window.showActionError = showActionError;
window.showActionSuccess = showActionSuccess;
