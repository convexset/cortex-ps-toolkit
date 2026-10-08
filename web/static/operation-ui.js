/** Shared operation plan confirm + copy mode controls. */

function planCounts(plan) {
  if (plan.summary) {
    return {
      total: plan.summary.total ?? 0,
      copy: plan.summary.create ?? 0,
      update: plan.summary.update ?? 0,
      skip: plan.summary.skip ?? 0,
      conflict: plan.summary.abort ?? 0,
    };
  }
  return plan.counts || { total: 0, copy: 0, update: 0, skip: 0, conflict: 0 };
}

function planWouldTakeNoAction(plan) {
  if (plan.would_abort) return true;
  const c = planCounts(plan);
  return (c.copy || 0) === 0 && (c.update || 0) === 0;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderOperationPlan(plan, { itemLabel = "item" } = {}) {
  const c = planCounts(plan);
  const parts = [];
  parts.push(`<div class="op-plan-summary">`);
  parts.push(`<p><strong>${escapeHtml(plan.operation || "copy")}</strong> · ${escapeHtml(plan.source_profile)} → ${escapeHtml(plan.target_profile)}</p>`);
  if (plan.mode_description) {
    parts.push(`<p class="op-plan-mode">${escapeHtml(plan.mode_description)}</p>`);
  }
  parts.push(
    `<p class="meta">Create ${c.copy}, update ${c.update}, skip ${c.skip}` +
      (c.conflict ? `, blocked ${c.conflict}` : "") +
      ` · ${c.total} ${escapeHtml(itemLabel)}(s)</p>`,
  );
  parts.push(`</div>`);

  if (plan.risks?.length) {
    parts.push(`<details class="op-plan-risks" open><summary>Risks (${plan.risks.length})</summary><ul>`);
    for (const risk of plan.risks) {
      parts.push(`<li class="severity-${escapeHtml(risk.severity || "high")}">${escapeHtml(risk.message || "")}</li>`);
    }
    parts.push(`</ul></details>`);
  }

  if (plan.warnings?.length) {
    parts.push(`<details class="op-plan-warnings"><summary>Warnings (${plan.warnings.length})</summary><ul>`);
    for (const w of plan.warnings) {
      parts.push(`<li>${escapeHtml(w.message || w)}</li>`);
    }
    parts.push(`</ul></details>`);
  }

  if (plan.steps?.length) {
    parts.push(`<details class="op-plan-steps"><summary>Execution steps</summary><ol>`);
    for (const step of plan.steps) {
      parts.push(`<li>${escapeHtml(step.label || "")}</li>`);
    }
    parts.push(`</ol></details>`);
  }

  if (plan.binding_table?.length) {
    parts.push(
      `<details class="op-plan-bindings"><summary>Binding preview (${plan.binding_table.length})</summary>`,
    );
    parts.push(`<table class="op-plan-table"><thead><tr><th>Playbook</th><th>Task</th><th>Issue</th></tr></thead><tbody>`);
    for (const row of plan.binding_table.slice(0, 40)) {
      parts.push(
        `<tr><td>${escapeHtml(row.playbook_name || "")}</td><td>${escapeHtml(String(row.task_id || ""))}</td><td>${escapeHtml(row.error || "")}</td></tr>`,
      );
    }
    if (plan.binding_table.length > 40) {
      parts.push(`<tr><td colspan="3">… ${plan.binding_table.length - 40} more</td></tr>`);
    }
    parts.push(`</tbody></table></details>`);
  }

  const items = plan.items || [];
  if (items.length) {
    parts.push(`<details class="op-plan-items"><summary>Items (${items.length})</summary>`);
    parts.push(`<table class="op-plan-table"><thead><tr><th>Name</th><th>Action</th><th>Notes</th></tr></thead><tbody>`);
    for (const item of items.slice(0, 50)) {
      const note = item.proposed_name ? `→ ${item.proposed_name}` : item.reason || "";
      parts.push(
        `<tr><td>${escapeHtml(item.name || "")}</td><td>${escapeHtml(item.action || "")}</td><td>${escapeHtml(note)}</td></tr>`,
      );
    }
    if (items.length > 50) {
      parts.push(`<tr><td colspan="3">… ${items.length - 50} more</td></tr>`);
    }
    parts.push(`</tbody></table></details>`);
  }

  if (plan.would_abort) {
    parts.push(`<p class="op-plan-abort"><strong>No upload will run.</strong> ${escapeHtml(plan.abort_reason || "Resolve conflicts or change copy mode.")}</p>`);
  }

  return parts.join("\n");
}

async function confirmOperation({ title, plan, proceedLabel = "Proceed", itemLabel = "item" }) {
  const html = renderOperationPlan(plan, { itemLabel });
  const needsRiskAck = (plan.risks || []).some((r) => r.severity === "high");
  const message = needsRiskAck
    ? `${html}<label class="op-risk-ack checkbox"><input type="checkbox" id="op-risk-ack-cb" /> I understand the risks above</label>`
    : html;

  if (typeof showConfirmDialog !== "function") {
    return window.confirm(plan.would_abort ? "Plan would abort. Continue anyway?" : "Proceed with operation?");
  }

  const proceed = await showConfirmDialog({
    title,
    message,
    proceedLabel,
    html: true,
    proceedEnabled: () => !needsRiskAck || document.getElementById("op-risk-ack-cb")?.checked,
  });
  return proceed;
}

function readCopyModeFromRow(prefix) {
  const selected = document.querySelector(`input[name="${prefix}-copy-mode"]:checked`);
  const mode = selected?.value || "skip";
  const suffixEl = document.getElementById(`${prefix}-copy-rename-suffix`);
  const rename_suffix = mode === "copy_as_new" ? (suffixEl?.value || "_copy").trim() : "";
  const overwrite = mode === "overwrite";
  const stop_on_conflict = mode === "stop_on_conflict";
  return { copy_mode: mode === "stop_on_conflict" ? "skip" : mode, overwrite, stop_on_conflict, rename_suffix };
}

function bindCopyModeRadios(prefix) {
  const radios = document.querySelectorAll(`input[name="${prefix}-copy-mode"]`);
  const suffixWrap = document.getElementById(`${prefix}-copy-rename-suffix-wrap`);
  const sync = () => {
    const mode = document.querySelector(`input[name="${prefix}-copy-mode"]:checked`)?.value;
    if (suffixWrap) {
      suffixWrap.classList.toggle("hidden", mode !== "copy_as_new");
    }
  };
  radios.forEach((el) => el.addEventListener("change", sync));
  sync();
}

function appendCopyModeControls(copyRowEl, prefix) {
  if (!copyRowEl || copyRowEl.querySelector(`.copy-mode-fieldset[data-prefix="${prefix}"]`)) return;
  const fieldset = document.createElement("fieldset");
  fieldset.className = "copy-mode-fieldset";
  fieldset.dataset.prefix = prefix;
  fieldset.innerHTML = `
    <legend>Copy mode</legend>
    <label class="checkbox"><input type="radio" name="${prefix}-copy-mode" value="skip" checked /> Skip existing on target</label>
    <label class="checkbox"><input type="radio" name="${prefix}-copy-mode" value="stop_on_conflict" /> Stop if any name exists</label>
    <label class="checkbox"><input type="radio" name="${prefix}-copy-mode" value="overwrite" /> Overwrite existing</label>
    <label class="checkbox"><input type="radio" name="${prefix}-copy-mode" value="copy_as_new" /> Copy as new name</label>
    <span id="${prefix}-copy-rename-suffix-wrap" class="copy-rename-suffix-wrap hidden">
      <label>Suffix for selected items
        <input type="text" id="${prefix}-copy-rename-suffix" value="_copy" size="8" />
      </label>
    </span>`;
  copyRowEl.insertBefore(fieldset, copyRowEl.querySelector("button.primary"));
  bindCopyModeRadios(prefix);
  const legacyOverwrite = document.getElementById(`${prefix}-copy-overwrite`) || document.getElementById("copy-overwrite");
  const legacyStop = document.getElementById(`${prefix}-copy-stop-on-conflict`) || document.getElementById("copy-stop-on-conflict");
  if (legacyOverwrite) legacyOverwrite.closest("label")?.classList.add("hidden");
  if (legacyStop) legacyStop.closest("label")?.classList.add("hidden");
}

function mergeCopyPayload(base, prefix) {
  const modeFields = readCopyModeFromRow(prefix);
  return { ...base, ...modeFields };
}
