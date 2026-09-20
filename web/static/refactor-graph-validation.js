/** Error-handling match preview helpers for the refactor panel (analysis tree). */

function refactorTaskSortKey(taskId) {
  const text = String(taskId);
  return /^\d+$/.test(text) ? [0, text.padStart(20, "0")] : [1, text];
}

function refactorCompareTaskIds(a, b) {
  const ka = refactorTaskSortKey(a);
  const kb = refactorTaskSortKey(b);
  if (ka[0] !== kb[0]) return ka[0] - kb[0];
  return ka[1].localeCompare(kb[1]);
}

function refactorTaskName(node) {
  return String(node?.task?.name || node?.task?.Name || "");
}

function refactorTaskType(node) {
  return String(node?.type || "unknown");
}

function refactorInnerTask(node) {
  return node?.task || {};
}

function refactorHasScriptBinding(node) {
  const inner = refactorInnerTask(node);
  return !!(
    inner.scriptId ||
    inner.scriptid ||
    inner.scriptName ||
    inner.scriptname ||
    inner.script
  );
}

function refactorIsRegularScriptTask(node) {
  return refactorTaskType(node) === "regular" && refactorHasScriptBinding(node);
}

function refactorScriptArgSimple(args, key) {
  const entry = args?.[key] ?? args?.[key.toLowerCase()];
  if (entry == null) return null;
  if (typeof entry === "object" && entry.simple != null) return String(entry.simple);
  return String(entry);
}

function refactorReadTaskErrorState(rawTask) {
  const args = rawTask?.scriptArguments || rawTask?.scriptarguments || {};
  const retryCount = refactorScriptArgSimple(args, "retry-count");
  const retryInterval = refactorScriptArgSimple(args, "retry-interval");
  const continueOnError = rawTask?.continueOnError ?? rawTask?.continueonerror;
  const continueOnErrorType = String(rawTask?.continueOnErrorType ?? rawTask?.continueonerrortype ?? "");
  const next = rawTask?.nextTasks || rawTask?.nexttasks || {};
  const hasErrorPath = Object.prototype.hasOwnProperty.call(next, "#error#");

  let errorHandling = "stop";
  if (continueOnErrorType === "errorPath") {
    errorHandling = "error-path";
  } else if (continueOnError === true) {
    errorHandling = "continue";
  }

  const retry =
    retryCount != null && retryCount !== ""
      ? `${retryCount} × every ${retryInterval || "?"}s`
      : "none";

  return {
    retry_count: retryCount,
    retry_interval: retryInterval,
    retry_label: retry,
    error_handling: errorHandling,
    continue_on_error: continueOnError,
    continue_on_error_type: continueOnErrorType || "",
    has_error_path: hasErrorPath,
  };
}

function refactorTaskTitleMatches(matchState, title) {
  const pattern = String(matchState?.pattern || "").trim();
  if (!pattern) {
    return false;
  }
  const hay = matchState.caseInsensitive ? String(title || "").toLowerCase() : String(title || "");
  const needle = matchState.caseInsensitive ? pattern.toLowerCase() : pattern;
  if (matchState.matchMode === "equals") {
    return hay === needle;
  }
  return hay.includes(needle);
}

function refactorFindErrorHandlingMatches(analysisData, matchState) {
  const matches = [];
  const flowGraphs = analysisData?.flow_graphs || [];
  for (let flowIndex = 0; flowIndex < flowGraphs.length; flowIndex += 1) {
    const entry = flowGraphs[flowIndex];
    for (const node of entry.graph?.nodes || []) {
      const rawTask = node.raw_task;
      if (!rawTask || !refactorIsRegularScriptTask(rawTask)) {
        continue;
      }
      const title = refactorTaskName(rawTask) || node.label || node.id;
      if (!refactorTaskTitleMatches(matchState, title)) {
        continue;
      }
      const inner = refactorInnerTask(rawTask);
      const errorState = refactorReadTaskErrorState(rawTask);
      matches.push({
        flow_index: flowIndex,
        playbook_name: entry.playbook_name,
        playbook_role: entry.role || "sub",
        task_id: String(node.id),
        title,
        task_type: refactorTaskType(rawTask),
        script_name: node.script_name || inner.scriptName || inner.scriptname || inner.script || "",
        script_binding: node.script_binding || inner.scriptName || inner.script || inner.scriptId || "",
        reachable: node.reachable !== false,
        ...errorState,
      });
    }
  }
  matches.sort((a, b) => {
    const pb = a.playbook_name.localeCompare(b.playbook_name);
    if (pb !== 0) return pb;
    return refactorCompareTaskIds(a.task_id, b.task_id);
  });
  return matches;
}

window.RefactorGraphValidation = {
  compareTaskIds: refactorCompareTaskIds,
  findErrorHandlingMatches: refactorFindErrorHandlingMatches,
};
