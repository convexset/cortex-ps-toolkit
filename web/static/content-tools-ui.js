/** Shared grid + bulk copy/delete for playbooks and scripts. */

function initContentTools(spec) {
  const {
    resource,
    gridSelector,
    metaId,
    refreshBtnId,
    selectAllVisibleBtnId,
    selectAllBtnId,
    selectNoneBtnId,
    deleteBtnId,
    copyBtnId,
    shallowCopyBtnId = null,
    selectionCountId,
    copyTargetId,
    copyOverwriteId,
    copyStopId,
    copyPostDiffId,
    copyResultId,
    deleteResultId,
    deleteDialogId,
    deleteFormId,
    deleteDialogTextId,
    deleteConfirmInputId,
    deleteSubmitId,
    deleteCancelId,
    idsKey,
    itemLabel,
    columns,
    searchInputId,
    viewBtnId,
    enableRowView = false,
  } = spec;

  let table = null;
  let gridSearch = null;

  function getSelectedRows() {
    if (gridSearch) {
      return gridSearch.getSelectedData();
    }
    return table ? table.getSelectedData() : [];
  }

  function updateSelectionCount() {
    const el = document.getElementById(selectionCountId);
    if (!el) return;
    const count = getSelectedRows().length;
    const pluralLabel = count === 1 ? itemLabel : `${itemLabel}s`;
    if (el.classList.contains("selection-count-badge")) {
      el.textContent = count === 0 ? "None selected" : `${count} ${pluralLabel} selected`;
    } else {
      el.textContent = `${count} selected`;
    }
    el.classList.toggle("has-selection", count > 0);
    el.setAttribute("aria-label", `${count} ${pluralLabel} selected`);
  }

  function initGrid() {
    table = new Tabulator(gridSelector, {
      height: typeof cptkGridHeight === "function" ? cptkGridHeight("default") : "420px",
      layout: "fitColumns",
      selectableRows: true,
      placeholder: `No cached ${resource} — click Refresh cache`,
      columns: cptkEnhanceColumns([
        {
          formatter: "rowSelection",
          hozAlign: "center",
          headerSort: false,
          width: 44,
          frozen: true,
          title: "",
        },
        ...columns,
      ]),
    });
    table.on("rowSelectionChanged", updateSelectionCount);
    if (enableRowView) {
      table.on("rowDblClick", (_event, row) => {
        void viewSelectedRow(row.getData());
      });
    }
    const searchInput = searchInputId ? document.getElementById(searchInputId) : null;
    if (searchInput) {
      gridSearch = attachGridSearch(table, searchInput, {
        onSelectionChange: updateSelectionCount,
      });
    }
  }

  function activeProfile() {
    return document.getElementById("active-profile").value;
  }

  async function loadForActiveProfile() {
    const profile = activeProfile();
    if (!profile || !table) return;
    localStorage.setItem("cptk_active_profile", profile);
    document.getElementById(metaId).textContent = "Loading…";
    try {
      const data = await withLoader(
        () => api(`/api/${resource}?profile=${encodeURIComponent(profile)}`),
        `Loading ${resource}…`,
      );
      table.setData(data[resource] || []);
      if (gridSearch) {
        gridSearch.clearSelection();
        gridSearch.applySearch();
      } else {
        table.deselectRow();
      }
      const metaLine =
        typeof formatCacheMetaLine === "function"
          ? formatCacheMetaLine(data, itemLabel)
          : `${data.count || 0} ${itemLabel}(s) · ${data.refreshed_at ? `Cached ${formatLocalDateTime(data.refreshed_at)}` : "Not cached yet"}`;
      document.getElementById(metaId).textContent = metaLine;
      updateSelectionCount();
    } catch (err) {
      document.getElementById(metaId).textContent = `Error: ${err.message}`;
      table.clearData();
      updateSelectionCount();
    }
  }

  async function refreshCache() {
    const profile = activeProfile();
    try {
      let data;
      if (window.cptkWs?.isConnected?.()) {
        try {
          const wsResult = await window.cptkWs.submitJob("cache.refresh", { profile, scope: resource });
          data = wsResult?.[resource] || wsResult;
        } catch (wsErr) {
          console.warn("WebSocket cache refresh failed, falling back to REST:", wsErr);
        }
      }
      if (!data) {
        data = await withLoader(
          () =>
            api(`/api/${resource}/refresh`, {
              method: "POST",
              body: JSON.stringify({ profile }),
            }),
          `Refreshing ${resource} cache…`,
        );
      }
      let meta =
        typeof formatCacheMetaLine === "function"
          ? formatCacheMetaLine({ ...data, cache: { ...(data.cache || {}), stale: false, age_label: "just refreshed" } }, itemLabel)
          : `${data.count} ${itemLabel}(s) · Refreshed ${data.refreshed_at ? formatLocalDateTime(data.refreshed_at) : "now"}`;
      if (data.warning) {
        meta += ` · ${data.warning}`;
      }
      document.getElementById(metaId).textContent = meta;
      await loadForActiveProfile();
    } catch (err) {
      alert(`Refresh failed: ${err.message}`);
    }
  }

  const copyModePrefix = resource === "playbooks" ? "playbooks" : resource;

  function copyOptionsPayload(source, target, itemIds) {
    const payload = {
      source_profile: source,
      target_profile: target,
      [idsKey]: itemIds,
    };
    if (copyPostDiffId) {
      payload.post_copy_diff = document.getElementById(copyPostDiffId)?.checked ?? false;
    }
    if (typeof mergeCopyPayload === "function") {
      return mergeCopyPayload(payload, copyModePrefix);
    }
    payload.overwrite = document.getElementById(copyOverwriteId).checked;
    payload.stop_on_conflict = document.getElementById(copyStopId).checked;
    return payload;
  }

  function planWouldTakeNoAction(plan) {
    if (plan.would_abort) return true;
    const counts = plan.summary || plan.counts || {};
    return (counts.create ?? counts.copy ?? 0) === 0 && (counts.update ?? 0) === 0;
  }

  function formatCopySummary(plan) {
    const noAction = planWouldTakeNoAction(plan);
    const names = plan.items.map((item) => item.name).join(", ");
    const lines = [
      noAction
        ? `Copy ${plan.counts.total} ${itemLabel}(s) from ${plan.source_profile} to ${plan.target_profile}:`
        : `Copy ${plan.counts.total} ${itemLabel}(s) from ${plan.source_profile} to ${plan.target_profile}?`,
      "",
      `Names: ${names}`,
      "",
    ];

    if (plan.stop_on_conflict) {
      lines.push("Stop if name exists on target: Yes");
      if (plan.would_abort) {
        const conflictNames = plan.conflicts.map((item) => item.name).join(", ");
        lines.push(`${plan.counts.conflict} ${itemLabel}(s) already exist on target: ${conflictNames}`);
      } else {
        lines.push("No name conflicts on target.");
        lines.push(`${plan.counts.copy} new ${itemLabel}(s) will be created.`);
      }
    } else if (plan.overwrite) {
      lines.push(`Overwrite existing ${itemLabel}s: Yes`);
      if (plan.counts.update) lines.push(`${plan.counts.update} existing ${itemLabel}(s) will be updated.`);
      if (plan.counts.copy) lines.push(`${plan.counts.copy} new ${itemLabel}(s) will be created.`);
    } else {
      lines.push(`Overwrite existing ${itemLabel}s: No`);
      if (plan.counts.skip) {
        const skippedNames = plan.items
          .filter((item) => item.action === "skip")
          .map((item) => item.name)
          .join(", ");
        lines.push(`${plan.counts.skip} existing ${itemLabel}(s) will be skipped: ${skippedNames}`);
      }
      if (plan.counts.copy) lines.push(`${plan.counts.copy} new ${itemLabel}(s) will be created.`);
    }

    lines.push("", noAction ? "No action will be taken." : "Proceed with copy?");
    return lines.join("\n");
  }

  function formatDeleteConfirmSummary(plan) {
    const names = plan.items.map((item) => item.name).join(", ");
    const lines = [
      `Delete ${plan.counts.total} ${itemLabel}(s) from ${plan.profile}?`,
      "",
      `Names: ${names}`,
      "",
      `This permanently removes the selected ${itemLabel}(s) from the tenant.`,
    ];

    if (plan.counts.blocked_system) {
      const blocked = plan.items
        .filter((item) => item.action === "blocked_system")
        .map((item) => item.name)
        .join(", ");
      lines.push(
        `${plan.counts.blocked_system} system ${itemLabel}(s) cannot be deleted and will be reported as blocked: ${blocked}`,
      );
    }
    if (plan.counts.not_found) {
      const missing = plan.items
        .filter((item) => item.action === "not_found")
        .map((item) => item.name)
        .join(", ");
      lines.push(`${plan.counts.not_found} ${itemLabel}(s) were not found in cache: ${missing}`);
    }
    if (plan.counts.delete) {
      lines.push(`${plan.counts.delete} ${itemLabel}(s) will be deleted if you continue.`);
    } else {
      lines.push(`No ${itemLabel}(s) can be deleted.`);
    }

    lines.push("", plan.would_delete ? "Go ahead?" : "No action will be taken.");
    return lines.join("\n");
  }

  function promptDeleteTypeConfirm(plan) {
    return new Promise((resolve) => {
      const dialog = document.getElementById(deleteDialogId);
      const form = document.getElementById(deleteFormId);
      const input = document.getElementById(deleteConfirmInputId);
      const submit = document.getElementById(deleteSubmitId);
      const cancel = document.getElementById(deleteCancelId);
      const text = document.getElementById(deleteDialogTextId);
      let accepted = false;

      text.textContent = `You are about to delete ${plan.counts.delete} ${itemLabel}(s) from ${plan.profile}. This cannot be undone. Type DELETE to proceed.`;
      input.value = "";
      submit.disabled = true;

      const onInput = () => {
        submit.disabled = input.value !== "DELETE";
      };
      const cleanup = () => {
        input.removeEventListener("input", onInput);
        cancel.removeEventListener("click", onCancel);
        form.removeEventListener("submit", onSubmit);
      };
      const onCancel = () => {
        accepted = false;
        dialog.close();
      };
      const onSubmit = (event) => {
        event.preventDefault();
        if (input.value !== "DELETE") return;
        accepted = true;
        dialog.close();
      };

      input.addEventListener("input", onInput);
      cancel.addEventListener("click", onCancel);
      form.addEventListener("submit", onSubmit);
      dialog.addEventListener(
        "close",
        () => {
          cleanup();
          resolve(accepted);
        },
        { once: true },
      );
      dialog.showModal();
      input.focus();
    });
  }

  async function deleteSelected() {
    const profile = activeProfile();
    const selected = getSelectedRows();
    if (!selected.length) {
      alert(`Select one or more ${itemLabel}s to delete.`);
      return;
    }

    const itemIds = selected.map((row) => row.id);
    const resultEl = document.getElementById(deleteResultId);

    try {
      const plan = await withLoader(
        () =>
          api(`/api/${resource}/delete/preview`, {
            method: "POST",
            body: JSON.stringify({ profile, [idsKey]: itemIds }),
          }),
        `Checking ${resource}…`,
      );

      const proceedDelete =
        typeof confirmDeletePlan === "function"
          ? await confirmDeletePlan({
              title: "Confirm delete",
              preview: plan,
              proceedLabel: "Continue",
              itemLabel,
            })
          : typeof showConfirmDialog === "function"
            ? await showConfirmDialog({
                title: "Confirm delete",
                message: formatDeleteConfirmSummary(plan),
                proceedLabel: "Continue",
              })
            : window.confirm(formatDeleteConfirmSummary(plan));
      if (!proceedDelete) return;

      const typed = await promptDeleteTypeConfirm(plan);
      if (!typed) return;

      const data = await withLoader(
        () =>
          api(`/api/${resource}/delete`, {
            method: "POST",
            body: JSON.stringify({ profile, [idsKey]: itemIds }),
          }),
        `Deleting ${resource}…`,
      );
      resultEl.textContent = JSON.stringify(data, null, 2);
      resultEl.classList.remove("hidden");
      if (typeof showOutcomeDialog === "function" && typeof summarizeBulkDeleteResult === "function") {
        const summary = summarizeBulkDeleteResult(data, itemLabel);
        showOutcomeDialog(summary);
      }
      await refreshCache();
    } catch (err) {
      if (typeof showOutcomeDialog === "function") {
        showOutcomeDialog({ title: "Delete failed", message: err.message, success: false });
      } else {
        alert(`Delete failed: ${err.message}`);
      }
    }
  }

  async function copyShallowSelected(triggerButton = null) {
    if (resource !== "playbooks") return;
    const source = activeProfile();
    const target = document.getElementById(copyTargetId).value;
    const selected = getSelectedRows();
    if (!selected.length) {
      alert("Select one or more playbooks for shallow copy.");
      return;
    }
    if (source === target) {
      alert("Choose a different target profile.");
      return;
    }
    const playbookIds = selected.map((row) => row.id);
    const payload = copyOptionsPayload(source, target, playbookIds);
    const resultEl = document.getElementById(copyResultId);
    try {
      const plan = await withLoader(
        () =>
          api("/api/playbooks/copy-shallow/preview", {
            method: "POST",
            body: JSON.stringify(payload),
          }),
        "Checking shallow copy plan…",
      );
      if (planWouldTakeNoAction(plan)) {
        alert("No shallow copy actions in plan.");
        return;
      }
      const proceedCopy =
        typeof confirmCopyPlan === "function"
          ? await confirmCopyPlan({
              title: "Confirm shallow copy",
              preview: plan,
              proceedLabel: "Shallow copy",
              itemLabel,
              operation: "playbooks.copy_shallow",
              source_profile: source,
              target_profile: target,
            })
          : typeof confirmOperation === "function"
            ? await confirmOperation({ title: "Confirm shallow copy", plan, proceedLabel: "Shallow copy", itemLabel })
            : window.confirm("Proceed with shallow copy?");
      if (!proceedCopy) return;
      const copyProgress = createOperationProgress("Shallow copy playbooks");
      const data = await copyProgress.runCopy({
        startMessage: `Shallow copying ${playbookIds.length} playbook(s)…`,
        wsAction: "playbooks.copy_shallow",
        payload,
        httpCall: () =>
          api("/api/playbooks/copy-shallow", {
            method: "POST",
            body: JSON.stringify(payload),
          }),
        loaderMessage: "Shallow copying…",
        busyButton: triggerButton,
        busyLabel: "Copying…",
      });
      if (typeof presentCopyResultView === "function") {
        const blockId = copyResultId.replace(/-result$/, "-result-block");
        const alertsId = copyResultId.replace(/-result$/, "-alerts");
        presentCopyResultView({
          resultEl,
          blockEl: document.getElementById(blockId),
          alertsEl: document.getElementById(alertsId),
          data,
          collectAlerts: collectBulkCopyAlerts,
          itemLabel,
        });
      }
    } catch (err) {
      if (typeof showOutcomeDialog === "function") {
        showOutcomeDialog({ title: "Shallow copy failed", message: err.message, success: false });
      } else {
        alert(`Shallow copy failed: ${err.message}`);
      }
    }
  }

  async function copySelected(triggerButton = null) {
    const source = activeProfile();
    const target = document.getElementById(copyTargetId).value;
    const selected = getSelectedRows();
    if (!selected.length) {
      alert(`Select one or more ${itemLabel}s to copy.`);
      return;
    }
    if (source === target) {
      alert("Choose a different target profile.");
      return;
    }

    const itemIds = selected.map((row) => row.id);
    const payload = copyOptionsPayload(source, target, itemIds);
    const resultEl = document.getElementById(copyResultId);

    try {
      const plan = await withLoader(
        () =>
          api(`/api/${resource}/copy/preview`, {
            method: "POST",
            body: JSON.stringify(payload),
          }),
        "Checking copy plan…",
      );

      if (planWouldTakeNoAction(plan)) {
        alert(typeof renderOperationPlan === "function" ? "No copy actions in plan." : formatCopySummary(plan));
        return;
      }

      const proceedCopy =
        typeof confirmCopyPlan === "function"
          ? await confirmCopyPlan({
              title: "Confirm copy",
              preview: plan,
              proceedLabel: "Copy",
              itemLabel,
              operation: `${resource}.copy`,
              source_profile: source,
              target_profile: target,
            })
          : typeof confirmOperation === "function"
            ? await confirmOperation({ title: "Confirm copy", plan, proceedLabel: "Copy", itemLabel })
            : typeof showConfirmDialog === "function"
              ? await showConfirmDialog({
                  title: "Confirm copy",
                  message: formatCopySummary(plan),
                  proceedLabel: "Copy",
                })
              : window.confirm(formatCopySummary(plan));
      if (!proceedCopy) return;

      const copyProgress = createOperationProgress(`Copy ${resource}`);
      const data = await copyProgress.runCopy({
        startMessage: `Copying ${itemIds.length} ${itemLabel}(s) to ${target}…`,
        wsAction: `${resource}.copy`,
        payload,
        httpCall: () => api(`/api/${resource}/copy`, {
          method: "POST",
          body: JSON.stringify(payload),
        }),
        loaderMessage: `Copying ${resource}…`,
        busyButton: triggerButton,
        busyLabel: "Copying…",
      });
      if (typeof presentCopyResultView === "function") {
        const blockId = copyResultId.replace(/-result$/, "-result-block");
        const alertsId = copyResultId.replace(/-result$/, "-alerts");
        presentCopyResultView({
          resultEl,
          blockEl: document.getElementById(blockId),
          alertsEl: document.getElementById(alertsId),
          data,
          collectAlerts: collectBulkCopyAlerts,
          itemLabel,
        });
      } else {
        resultEl.textContent = JSON.stringify(data, null, 2);
        resultEl.classList.remove("hidden");
      }
      if (typeof showOutcomeDialog === "function" && typeof summarizeBulkCopyResult === "function") {
        const summary = summarizeBulkCopyResult(data, itemLabel);
        showOutcomeDialog(summary);
      } else if (data.aborted) {
        alert(data.reason || "Copy was aborted.");
      }
    } catch (err) {
      if (typeof showOutcomeDialog === "function") {
        showOutcomeDialog({ title: "Copy failed", message: err.message, success: false });
      } else {
        alert(`Copy failed: ${err.message}`);
      }
    }
  }

  async function viewSelectedRow(row = null) {
    const rows = row ? [row] : getSelectedRows();
    if (rows.length !== 1) {
      alert(`Select exactly one ${itemLabel} to view.`);
      return;
    }
    const selected = rows[0];
    const profile = activeProfile();
    const itemId = selected.id || selected.name;
    if (!profile || !itemId) {
      alert(`Select a profile and ${itemLabel} to view.`);
      return;
    }
    await openContentDetailViewer({
      title: selected.name || itemId,
      fetchUrl: `/api/${resource}/${encodeURIComponent(itemId)}?profile=${encodeURIComponent(profile)}`,
      loaderMessage: `Loading ${itemLabel}…`,
    });
  }

  function bindCopyOptionExclusivity() {
    const overwriteEl = document.getElementById(copyOverwriteId);
    const stopEl = document.getElementById(copyStopId);
    overwriteEl.addEventListener("change", () => {
      if (overwriteEl.checked) stopEl.checked = false;
    });
    stopEl.addEventListener("change", () => {
      if (stopEl.checked) overwriteEl.checked = false;
    });
  }

  function bindEvents() {
    document.getElementById(refreshBtnId).addEventListener("click", refreshCache);
    document.getElementById(copyBtnId).addEventListener("click", (event) => {
      copySelected(event.currentTarget);
    });
    if (shallowCopyBtnId) {
      document.getElementById(shallowCopyBtnId)?.addEventListener("click", (event) => {
        void copyShallowSelected(event.currentTarget);
      });
    }
    const copyRow = document.getElementById(copyBtnId)?.closest(".copy-row");
    if (copyRow && typeof appendCopyModeControls === "function") {
      appendCopyModeControls(copyRow, copyModePrefix);
      copyRow.addEventListener("cptk-open-rename-map", () => {
        const target = document.getElementById(copyTargetId)?.value;
        if (typeof openRenameMapEditor === "function") {
          void openRenameMapEditor(copyModePrefix, {
            items: getSelectedRows(),
            targetProfile: target,
            kind: resource === "playbooks" ? "playbooks" : resource,
          });
        }
      });
      const scheduleNameCheck = () => {
        const target = document.getElementById(copyTargetId)?.value;
        if (typeof scheduleCopyNameCheck === "function") {
          scheduleCopyNameCheck(copyModePrefix, {
            targetProfile: target,
            kind: resource === "playbooks" ? "playbooks" : resource,
            items: getSelectedRows(),
          });
        }
      };
      copyRow.addEventListener("cptk-copy-rename-changed", scheduleNameCheck);
      document.getElementById(copyTargetId)?.addEventListener("change", scheduleNameCheck);
    }
    document.getElementById(deleteBtnId).addEventListener("click", deleteSelected);
    const addBundleBtnId = `${resource}-add-to-bundle`;
    if (document.getElementById(addBundleBtnId)) {
      document.getElementById(addBundleBtnId).addEventListener("click", () => {
        const rows = getSelectedRows();
        if (!rows.length) {
          alert(`Select ${itemLabel}(s) to add to bundle.`);
          return;
        }
        const asset = resource === "playbooks" ? "playbooks" : resource === "scripts" ? "scripts" : resource;
        let added = 0;
        for (const row of rows) {
          if (typeof cptkAddToBundle === "function" && cptkAddToBundle(asset, row)) added += 1;
        }
        if (!added) alert("Selected items are already in the bundle.");
        else if (typeof showActionSuccess === "function") {
          showActionSuccess(`Added ${added} item(s). Open Bundles to review or copy.`, { title: "Bundle updated" });
        }
      });
    }
    if (viewBtnId) {
      document.getElementById(viewBtnId)?.addEventListener("click", () => {
        void viewSelectedRow();
      });
    }
    document.getElementById(selectAllVisibleBtnId).addEventListener("click", () => {
      if (gridSearch) {
        gridSearch.selectAllVisible();
      } else {
        table.selectRow("active");
        updateSelectionCount();
      }
    });
    document.getElementById(selectAllBtnId).addEventListener("click", () => {
      if (gridSearch) {
        gridSearch.selectAll();
      } else {
        table.selectRow("all");
        updateSelectionCount();
      }
    });
    document.getElementById(selectNoneBtnId).addEventListener("click", () => {
      if (gridSearch) {
        gridSearch.clearSelection();
      } else {
        table.deselectRow("all");
        updateSelectionCount();
      }
    });
    bindCopyOptionExclusivity();
  }

  initGrid();
  bindEvents();

  return {
    table,
    gridSearch,
    getSelectedRows,
    loadForActiveProfile,
    refreshCache,
    viewSelected: viewSelectedRow,
  };
}
