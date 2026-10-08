/** Shared operation plan confirm + copy mode controls. */

function isDeletePlan(plan) {
  return String(plan?.operation || "").includes(".delete");
}

function planCounts(plan) {
  if (plan.summary?.delete !== undefined) {
    return {
      total: plan.summary.total ?? 0,
      copy: plan.summary.delete ?? 0,
      update: 0,
      skip: plan.summary.skip ?? 0,
      conflict: plan.summary.blocked ?? plan.summary.abort ?? 0,
    };
  }
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

function planPreviewBody(preview) {
  if (!preview || typeof preview !== "object") {
    return preview;
  }
  if (preview.plan_version) {
    return preview;
  }
  const nested = preview.plan;
  if (nested && typeof nested === "object") {
    if (nested.plan_version) {
      return nested;
    }
    if (nested.items?.length || nested.entries?.length) {
      return { ...nested, abort_reason: preview.reason || nested.abort_reason };
    }
  }
  return preview;
}

function planEntryName(entry) {
  return (
    entry.name ||
    entry.target_name ||
    entry.source_name ||
    entry.lookup ||
    entry.integration_id ||
    entry.playbook_name ||
    entry.script_name ||
    entry.source_id ||
    entry.id ||
    entry.key_id ||
    entry.display ||
    "?"
  );
}

function normalizePlanAction(action) {
  const a = String(action || "skip");
  if (a === "missing") return "skip";
  if (a === "blocked_pack" || a === "blocked_non_copyable" || a === "incompatible") return "blocked";
  return a;
}

function normalizeConfirmPlan(
  preview,
  { operation = "copy", source_profile = "", target_profile = "", itemLabel = "item" } = {},
) {
  const body = planPreviewBody(preview);
  if (body?.plan_version) {
    return body;
  }
  const entries = body?.flat_items || body?.items || body?.entries || [];
  const items = entries.map((entry) => ({
    name: planEntryName(entry),
    action: normalizePlanAction(entry.action),
    reason: entry.reason,
    proposed_name: entry.proposed_name,
    kind: entry.kind,
  }));
  let create = 0;
  let update = 0;
  let skip = 0;
  let abort = 0;
  for (const item of items) {
    const action = item.action;
    if (action === "update") {
      update += 1;
    } else if (action === "copy" || action === "copy_as_new") {
      create += 1;
    } else if (action === "skip") {
      skip += 1;
    } else if (action === "conflict" || action === "blocked") {
      abort += 1;
    }
  }
  const stopOnConflict = Boolean(body?.stop_on_conflict);
  const hasConflicts = Boolean(body?.has_conflicts);
  const inferredAbort =
    Boolean(body?.would_abort) ||
    (hasConflicts && stopOnConflict) ||
    (stopOnConflict && abort > 0) ||
    body?.executed === false;
  const counts = body?.counts || {
    total: items.length,
    copy: create,
    update,
    skip,
    conflict: abort,
  };
  const warnings = [...(body?.warnings || [])];
  if (body?.missing_sub_playbooks?.length) {
    warnings.push({
      code: "MISSING_SUB_PLAYBOOKS",
      message: `${body.missing_sub_playbooks.length} referenced sub-playbook(s) are not in the copy plan — resolve before deep copy.`,
    });
  }
  if (body?.asset) {
    warnings.push({
      code: "DESIGN_ASSET",
      message: `Design asset kind: ${body.asset}`,
    });
  }

  return {
    plan_version: 1,
    operation: body?.operation || operation,
    source_profile: body?.source_profile || source_profile,
    target_profile: body?.target_profile || target_profile,
    items,
    summary: body?.summary || {
      total: items.length,
      create,
      update,
      skip,
      abort,
    },
    counts,
    would_abort: inferredAbort,
    abort_reason: body?.abort_reason || body?.error || preview?.reason,
    warnings: warnings.length ? warnings : undefined,
    risks: body?.risks,
    binding_table: body?.binding_table,
    sub_plans: body?.sub_plans,
    steps: body?.steps,
    mode_description: body?.mode_description,
    missing_sub_playbooks: body?.missing_sub_playbooks,
  };
}

function renderOperationPlan(plan, { itemLabel = "item" } = {}) {
  const c = planCounts(plan);
  const deletePlan = isDeletePlan(plan);
  const parts = [];
  parts.push(`<div class="op-plan-summary">`);
  if (deletePlan) {
    parts.push(
      `<p><strong>${escapeHtml(plan.operation || "delete")}</strong> · profile ${escapeHtml(plan.profile || plan.source_profile || "")}</p>`,
    );
  } else {
    parts.push(
      `<p><strong>${escapeHtml(plan.operation || "copy")}</strong> · ${escapeHtml(plan.source_profile)} → ${escapeHtml(plan.target_profile)}</p>`,
    );
  }
  if (plan.mode_description) {
    parts.push(`<p class="op-plan-mode">${escapeHtml(plan.mode_description)}</p>`);
  }
  if (deletePlan) {
    parts.push(
      `<p class="meta">Delete ${c.copy}, blocked ${c.conflict}, skip ${c.skip} · ${c.total} ${escapeHtml(itemLabel)}(s)</p>`,
    );
  } else {
    parts.push(
      `<p class="meta">Create ${c.copy}, update ${c.update}, skip ${c.skip}` +
        (c.conflict ? `, blocked ${c.conflict}` : "") +
        ` · ${c.total} ${escapeHtml(itemLabel)}(s)</p>`,
    );
  }
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

  if (!plan.binding_table?.length && plan.sub_plans?.length) {
    for (const sub of plan.sub_plans) {
      if (sub.phase === "playbooks" && sub.binding_table?.length) {
        plan = { ...plan, binding_table: sub.binding_table };
        break;
      }
    }
  }

  if (plan.sub_plans?.length) {
    parts.push(`<details class="op-plan-sub-plans"><summary>Phases (${plan.sub_plans.length})</summary>`);
    parts.push(`<table class="op-plan-table"><thead><tr><th>Phase</th><th>Items</th><th>Notes</th></tr></thead><tbody>`);
    for (const sub of plan.sub_plans) {
      const counts = sub.counts || {};
      const note = sub.would_abort
        ? "would abort"
        : `create ${counts.copy ?? 0}, update ${counts.update ?? 0}, skip ${counts.skip ?? 0}`;
      parts.push(
        `<tr><td>${escapeHtml(sub.phase || "?")}</td><td>${escapeHtml(String(sub.item_count ?? counts.total ?? "?"))}</td><td>${escapeHtml(note)}</td></tr>`,
      );
    }
    parts.push(`</tbody></table></details>`);
  }

  if (plan.binding_table?.length) {
    parts.push(
      `<details class="op-plan-bindings" open><summary>Unresolved playbook bindings (${plan.binding_table.length})</summary>`,
    );
    parts.push(
      `<p class="meta">Shallow playbook copy may succeed while these task bindings are missing on the target. Add scripts/sub-playbooks to the basket or copy dependencies first.</p>`,
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
    const msg = deletePlan
      ? plan.abort_reason || "Nothing in this selection can be deleted."
      : plan.abort_reason || "Resolve conflicts or change copy mode.";
    parts.push(
      `<p class="op-plan-abort"><strong>${deletePlan ? "Delete will not run." : "No upload will run."}</strong> ${escapeHtml(msg)}</p>`,
    );
  }

  return parts.join("\n");
}

async function confirmDeletePlan({ title, preview, proceedLabel = "Delete", itemLabel = "item" }) {
  const plan = preview?.plan_version
    ? preview
    : normalizeConfirmPlan(preview, { operation: "delete", itemLabel });
  if (!plan.would_delete && plan.would_delete !== undefined) {
    if (typeof showOutcomeDialog === "function") {
      showOutcomeDialog({
        title: "Nothing to delete",
        message: plan.abort_reason || "No deletable items in selection.",
        success: false,
      });
    } else {
      alert(plan.abort_reason || "Nothing to delete.");
    }
    return false;
  }
  if (typeof confirmOperation === "function") {
    return confirmOperation({ title, plan, proceedLabel, itemLabel });
  }
  return false;
}

async function confirmCopyPlan({
  title,
  preview,
  proceedLabel = "Proceed",
  itemLabel = "item",
  operation = "copy",
  source_profile = "",
  target_profile = "",
}) {
  const plan = preview?.plan_version
    ? preview
    : normalizeConfirmPlan(preview, { operation, source_profile, target_profile, itemLabel });
  if (typeof confirmOperation === "function") {
    return confirmOperation({ title, plan, proceedLabel, itemLabel });
  }
  if (typeof showConfirmDialog === "function" && typeof renderOperationPlan === "function") {
    return showConfirmDialog({
      title,
      message: renderOperationPlan(plan, { itemLabel }),
      proceedLabel,
      html: true,
    });
  }
  return window.confirm(plan.would_abort ? "Plan would abort. Continue anyway?" : "Proceed with operation?");
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

const cptkRenameMaps = window.__cptkRenameMaps || (window.__cptkRenameMaps = {});

function readRenameMap(prefix) {
  const stored = cptkRenameMaps[prefix];
  if (!stored || typeof stored !== "object") return {};
  return { ...stored };
}

function setRenameMap(prefix, map) {
  cptkRenameMaps[prefix] = { ...map };
  const statusEl = document.getElementById(`${prefix}-copy-rename-map-status`);
  if (statusEl) {
    const n = Object.keys(map || {}).length;
    statusEl.textContent = n ? `${n} override(s)` : "";
  }
}

function readCopyModeFromRow(prefix) {
  const selected = document.querySelector(`input[name="${prefix}-copy-mode"]:checked`);
  const mode = selected?.value || "skip";
  const suffixEl = document.getElementById(`${prefix}-copy-rename-suffix`);
  const rename_suffix = mode === "copy_as_new" ? (suffixEl?.value || "_copy").trim() : "";
  const overwrite = mode === "overwrite";
  const stop_on_conflict = mode === "stop_on_conflict";
  const postDiffEl = document.getElementById(`${prefix}-copy-post-diff`);
  const rename_map = mode === "copy_as_new" ? readRenameMap(prefix) : {};
  return {
    copy_mode: mode === "stop_on_conflict" ? "skip" : mode,
    overwrite,
    stop_on_conflict,
    rename_suffix,
    rename_map,
    post_copy_diff: postDiffEl?.checked ?? false,
  };
}

function bindCopyModeRadios(prefix) {
  const radios = document.querySelectorAll(`input[name="${prefix}-copy-mode"]`);
  const suffixWrap = document.getElementById(`${prefix}-copy-rename-suffix-wrap`);
  const mapWrap = document.getElementById(`${prefix}-copy-rename-map-wrap`);
  const sync = () => {
    const mode = document.querySelector(`input[name="${prefix}-copy-mode"]:checked`)?.value;
    const showRename = mode === "copy_as_new";
    if (suffixWrap) suffixWrap.classList.toggle("hidden", !showRename);
    if (mapWrap) mapWrap.classList.toggle("hidden", !showRename);
  };
  radios.forEach((el) => el.addEventListener("change", sync));
  sync();
}

async function openRenameMapEditor(prefix, { items = [], targetProfile = "", kind = "scripts", asset = null } = {}) {
  if (!items.length) {
    alert("Select items first, then edit per-item target names.");
    return;
  }
  const suffixEl = document.getElementById(`${prefix}-copy-rename-suffix`);
  const suffix = (suffixEl?.value || "_copy").trim();
  const existing = readRenameMap(prefix);
  const rows = items.map((item) => {
    const key = String(item.id || item.key || item.name || "");
    const source = String(item.name || key);
    const defaultProposed = `${source}${suffix}`;
    const proposed = existing[key] || defaultProposed;
    return { key, source, proposed };
  });
  const lines = rows
    .map(
      (row) =>
        `<tr data-key="${escapeHtml(row.key)}"><td>${escapeHtml(row.source)}</td>` +
        `<td><input type="text" class="rename-map-input" value="${escapeHtml(row.proposed)}" size="28" /></td></tr>`,
    )
    .join("");
  const html = `<p class="meta">Override target names for copy-as-new. Keys are tenant object ids.</p>
    <table class="op-plan-table rename-map-table"><thead><tr><th>Source name</th><th>Target name</th></tr></thead><tbody>${lines}</tbody></table>
    <p id="${prefix}-rename-map-check" class="meta rename-map-check-msg"></p>`;
  const proceed = await showConfirmDialog({
    title: "Per-item target names",
    message: html,
    proceedLabel: "Save overrides",
    html: true,
  });
  if (!proceed) return;
  const container = document.getElementById("confirm-dialog-message");
  const map = {};
  container?.querySelectorAll("tr[data-key]").forEach((tr) => {
    const key = tr.getAttribute("data-key") || "";
    const input = tr.querySelector(".rename-map-input");
    const value = (input?.value || "").trim();
    const source = rows.find((r) => r.key === key)?.source || "";
    const defaultProposed = `${source}${suffix}`;
    if (value && value !== defaultProposed) {
      map[key] = value;
    }
  });
  setRenameMap(prefix, map);
  if (targetProfile && typeof scheduleCopyNameCheck === "function") {
    scheduleCopyNameCheck(prefix, { targetProfile, kind, items, asset });
  }
}

let cptkNameCheckTimers = {};

function scheduleCopyNameCheck(prefix, { targetProfile, kind, items, asset = null }) {
  if (!targetProfile || !items?.length) return;
  clearTimeout(cptkNameCheckTimers[prefix]);
  cptkNameCheckTimers[prefix] = setTimeout(() => {
    void runCopyNameCheck(prefix, { targetProfile, kind, items, asset });
  }, 400);
}

async function runCopyNameCheck(prefix, { targetProfile, kind, items, asset = null }) {
  const modeFields = readCopyModeFromRow(prefix);
  if (modeFields.copy_mode !== "copy_as_new") return;
  const msgEl = document.getElementById(`${prefix}-copy-name-check-msg`);
  try {
    const body = {
      target_profile: targetProfile,
      kind,
      items: items.map((row) => ({ id: row.id || row.key, name: row.name })),
      copy_mode: "copy_as_new",
      rename_suffix: modeFields.rename_suffix,
      rename_map: modeFields.rename_map,
    };
    if (asset) body.asset = asset;
    const result = await api("/api/copy/name-check", { method: "POST", body: JSON.stringify(body) });
    const collisions = (result.checks || []).filter((c) => c.exists);
    if (msgEl) {
      msgEl.textContent = collisions.length
        ? `⚠ ${collisions.length} proposed name(s) already on target: ${collisions.map((c) => c.proposed_name).join(", ")}`
        : "✓ Proposed names available on target (cache)";
      msgEl.classList.toggle("rename-map-collision", collisions.length > 0);
    }
  } catch (err) {
    if (msgEl) msgEl.textContent = `Name check failed: ${err.message}`;
  }
}

function fieldHelpIcon(tooltipText) {
  const t = escapeHtml(String(tooltipText));
  return `<span class="field-help-icon" tabindex="0" role="img" aria-label="${t}" title="${t}">?</span>`;
}

function bindFieldHelpIcons(root) {
  root.querySelectorAll(".field-help-icon").forEach((el) => {
    const stop = (event) => {
      event.preventDefault();
      event.stopPropagation();
    };
    el.addEventListener("mousedown", stop);
    el.addEventListener("click", stop);
  });
}

function appendCopyModeControls(copyRowEl, prefix) {
  if (!copyRowEl || copyRowEl.querySelector(`.copy-mode-fieldset[data-prefix="${prefix}"]`)) return;
  const fieldset = document.createElement("fieldset");
  fieldset.className = "copy-mode-fieldset";
  fieldset.dataset.prefix = prefix;
  const helpCopyMode = fieldHelpIcon(
    "When a selected item's name already exists on the target tenant, choose whether to skip, abort, overwrite, or create under a new name.",
  );
  const helpSkip = fieldHelpIcon(
    "Do not upload items whose names already exist on the target; leave those target objects unchanged.",
  );
  const helpStop = fieldHelpIcon(
    "Abort the entire copy if any selected item's name already exists on the target (nothing is uploaded).",
  );
  const helpOverwrite = fieldHelpIcon(
    "Replace target objects that have the same name with the source version (update in place).",
  );
  const helpCopyAsNew = fieldHelpIcon(
    "Alternative to skip or overwrite when names collide: create a new object on the target by appending the suffix (e.g. MyScript → MyScript_copy). The original target object is kept. Items with no name conflict keep their source names. The copy is blocked if the proposed new name is already taken. Integrations ignore copy-as-new. Design / object-setup uses the suffix as name_suffix when provided.",
  );
  const helpSuffix = fieldHelpIcon(
    "Text appended to each colliding item's name when Copy as new name is selected (default _copy, e.g. ProcessEmail → ProcessEmail_copy).",
  );
  const helpPostDiff = fieldHelpIcon(
    "After a successful copy, compare source vs target read-back and show ignored vs flagged field deltas.",
  );
  fieldset.innerHTML = `
    <legend>Copy mode ${helpCopyMode}</legend>
    <label class="checkbox copy-mode-option"><input type="radio" name="${prefix}-copy-mode" value="skip" checked /> Skip existing on target ${helpSkip}</label>
    <label class="checkbox copy-mode-option"><input type="radio" name="${prefix}-copy-mode" value="stop_on_conflict" /> Stop if any name exists ${helpStop}</label>
    <label class="checkbox copy-mode-option"><input type="radio" name="${prefix}-copy-mode" value="overwrite" /> Overwrite existing ${helpOverwrite}</label>
    <label class="checkbox copy-mode-option"><input type="radio" name="${prefix}-copy-mode" value="copy_as_new" /> Copy as new name ${helpCopyAsNew}</label>
    <span id="${prefix}-copy-rename-suffix-wrap" class="copy-rename-suffix-wrap hidden">
      <label class="copy-mode-suffix-label">Suffix for colliding names ${helpSuffix}
        <input type="text" id="${prefix}-copy-rename-suffix" value="_copy" size="8" />
      </label>
    </span>
    <span id="${prefix}-copy-rename-map-wrap" class="copy-rename-map-wrap hidden">
      <button type="button" class="secondary compact" id="${prefix}-copy-rename-map-btn">Per-item names…</button>
      <span id="${prefix}-copy-rename-map-status" class="meta rename-map-status"></span>
      <span id="${prefix}-copy-name-check-msg" class="meta copy-name-check-msg"></span>
    </span>
    <label class="checkbox copy-post-diff-label">
      <input type="checkbox" id="${prefix}-copy-post-diff" />
      Diff after copy ${helpPostDiff}
    </label>`;
  copyRowEl.insertBefore(fieldset, copyRowEl.querySelector("button.primary"));
  bindFieldHelpIcons(fieldset);
  bindCopyModeRadios(prefix);
  const suffixInput = document.getElementById(`${prefix}-copy-rename-suffix`);
  suffixInput?.addEventListener("input", () => {
    copyRowEl.dispatchEvent(new CustomEvent("cptk-copy-rename-changed", { bubbles: true }));
  });
  document.getElementById(`${prefix}-copy-rename-map-btn`)?.addEventListener("click", () => {
    copyRowEl.dispatchEvent(new CustomEvent("cptk-open-rename-map", { bubbles: true }));
  });
  const legacyOverwrite = document.getElementById(`${prefix}-copy-overwrite`) || document.getElementById("copy-overwrite");
  const legacyStop = document.getElementById(`${prefix}-copy-stop-on-conflict`) || document.getElementById("copy-stop-on-conflict");
  if (legacyOverwrite) legacyOverwrite.closest("label")?.classList.add("hidden");
  if (legacyStop) legacyStop.closest("label")?.classList.add("hidden");
}

function mergeCopyPayload(base, prefix) {
  const modeFields = readCopyModeFromRow(prefix);
  const payload = { ...base, ...modeFields };
  if (!Object.keys(modeFields.rename_map || {}).length) {
    delete payload.rename_map;
  }
  return payload;
}

window.normalizeConfirmPlan = normalizeConfirmPlan;
window.confirmCopyPlan = confirmCopyPlan;
window.confirmOperation = confirmOperation;
window.renderOperationPlan = renderOperationPlan;
window.planWouldTakeNoAction = planWouldTakeNoAction;
window.planCounts = planCounts;
window.appendCopyModeControls = appendCopyModeControls;
window.mergeCopyPayload = mergeCopyPayload;
window.readCopyModeFromRow = readCopyModeFromRow;
window.confirmDeletePlan = confirmDeletePlan;
window.openRenameMapEditor = openRenameMapEditor;
window.scheduleCopyNameCheck = scheduleCopyNameCheck;
window.runCopyNameCheck = runCopyNameCheck;
window.readRenameMap = readRenameMap;
window.setRenameMap = setRenameMap;
window.isDeletePlan = isDeletePlan;
