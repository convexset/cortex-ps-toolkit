/** Self-dismissing toasts for playbook analysis cache / tenant fetch needs. */

const ANALYSIS_FETCH_TOAST_MS = 8000;

function formatScopeList(scopes) {
  const labels = typeof CORE_CACHE_LABELS !== "undefined" ? CORE_CACHE_LABELS : {};
  return (scopes || []).map((scope) => labels[scope] || scope).join(", ");
}

function showAnalysisFetchToast({ title, message, level = "info", autoDismissMs = ANALYSIS_FETCH_TOAST_MS }) {
  if (window.cptkWs?.showToast) {
    window.cptkWs.showToast({ level, title, message, autoDismissMs });
  }
}

function formatSampleNames(rows, max = 3) {
  const list = rows || [];
  const sample = list
    .slice(0, max)
    .map((row) => row.name || row.id)
    .join(", ");
  const extra = list.length > max ? ` (+${list.length - max} more)` : "";
  return { sample, extra, count: list.length };
}

function notifyAnalysisFetchPlan(plan) {
  if (!plan || typeof plan !== "object") {
    return;
  }

  const indexCount = plan.index_playbook_count;
  const bodiesOnDisk = plan.playbook_bodies_on_disk_count;
  if (indexCount != null && bodiesOnDisk != null) {
    showAnalysisFetchToast({
      title: "Two-layer playbook cache",
      message: `Index lists ${indexCount} playbook(s) from the last refresh. ${bodiesOnDisk} full YAML file(s) are stored locally under playbooks/bodies/ (downloaded on demand, not with index refresh).`,
      autoDismissMs: 9000,
    });
  }

  const stale = plan.stale_scopes || [];
  if (stale.length) {
    showAnalysisFetchToast({
      title: "Elective index age",
      message: `The ${formatScopeList(stale)} index cache is older than the elective TTL. Analysis still uses those lists; only missing playbook YAML triggers tenant downloads.`,
    });
  }

  const missingFile = plan.playbook_bodies_missing_file_count ?? 0;
  const notInIndex = plan.playbook_bodies_not_in_index_count ?? 0;
  const modifiedMismatch = plan.playbook_bodies_modified_mismatch_count ?? 0;
  const needed = plan.playbook_bodies_needed || [];

  if (missingFile > 0) {
    const rows = needed.filter((row) => row.reason === "missing_file");
    const { sample, extra } = formatSampleNames(rows);
    showAnalysisFetchToast({
      title: "YAML not downloaded yet",
      message: `${missingFile} playbook(s) appear in the index but have no local task YAML yet: ${sample}${extra}. These will be fetched from the tenant.`,
    });
  }

  if (modifiedMismatch > 0) {
    const rows = needed.filter((row) => row.reason === "modified_mismatch");
    const { sample, extra } = formatSampleNames(rows);
    showAnalysisFetchToast({
      title: "Local YAML out of sync",
      message: `${modifiedMismatch} cached file(s) no longer match the index id/name (${sample}${extra}). Analysis will re-download those playbooks.`,
      level: "warning",
    });
  }

  if (notInIndex > 0) {
    const rows = needed.filter((row) => row.reason === "not_in_index");
    const { sample, extra } = formatSampleNames(rows);
    showAnalysisFetchToast({
      title: "Unresolved playbook reference",
      message: `${notInIndex} reference(s) are not in the cached index (${sample}${extra}). Refresh the playbook list or fix the reference.`,
      level: "warning",
    });
  }

  const fetchTotal = plan.playbook_bodies_needed_count ?? 0;
  const cachedCount = plan.playbook_bodies_cached_count ?? 0;
  if (fetchTotal === 0 && cachedCount > 0 && !stale.length) {
    showAnalysisFetchToast({
      title: "Playbook analysis",
      message: `${cachedCount} playbook YAML file(s) in this tree are already available locally — no tenant downloads expected.`,
      autoDismissMs: 5000,
    });
  }
}

function notifyAnalysisFetchSummary(summary) {
  if (!summary || typeof summary !== "object") {
    return;
  }
  const restamped = summary.playbooks_restamped_count ?? (summary.playbooks_restamped || []).length;
  if (restamped > 0) {
    const { sample, extra } = formatSampleNames(summary.playbooks_restamped || []);
    showAnalysisFetchToast({
      title: "Index metadata synced",
      message: `Reused ${restamped} local YAML file(s) after an index refresh (updated modified stamp only): ${sample}${extra}.`,
      level: "success",
      autoDismissMs: 6000,
    });
  }
  const fetched = summary.playbooks_fetched || [];
  const count = summary.playbooks_fetched_count ?? fetched.length;
  if (count) {
    const { sample, extra } = formatSampleNames(fetched);
    showAnalysisFetchToast({
      title: "Download complete",
      message: `Downloaded ${count} playbook YAML file(s) from the tenant: ${sample}${extra}.`,
      level: "success",
      autoDismissMs: 5000,
    });
  }
  const scripts = summary.scripts_fetched || [];
  const scriptCount = summary.scripts_fetched_count ?? scripts.length;
  if (scriptCount) {
    const { sample, extra } = formatSampleNames(scripts);
    showAnalysisFetchToast({
      title: "Scripts cached",
      message: `Downloaded ${scriptCount} automation script body file(s): ${sample}${extra}.`,
      level: "success",
      autoDismissMs: 5000,
    });
  }
}

async function runPlaybookAnalysisJob(profile, playbookId, progress, options = {}) {
  const cacheOnly = options.cacheOnly !== false;
  const payload = {
    profile,
    playbook_id: playbookId,
    cache_only: cacheOnly,
    skip_cache_refresh: true,
  };
  const query = new URLSearchParams({
    profile,
    cache_only: cacheOnly ? "true" : "false",
    skip_cache_refresh: "true",
  });
  const startMessage = options.startMessage || "Analyzing playbook…";

  if (window.cptkWs?.isConnected?.()) {
    try {
      const result = await window.cptkWs.submitJob(
        "playbooks.analyze",
        payload,
        progress?.wsJobOptions?.({ startMessage, timeoutMs: options.timeoutMs ?? 900000 }) || {
          timeoutMs: options.timeoutMs ?? 900000,
        },
      );
      notifyAnalysisFetchSummary(result?.fetch_summary);
      return result;
    } finally {
      progress?.clear?.();
    }
  }
  progress?.show?.(startMessage);
  try {
    const data = await api(`/api/playbooks/${encodeURIComponent(playbookId)}/analysis?${query.toString()}`);
    notifyAnalysisFetchSummary(data?.fetch_summary);
    return data;
  } finally {
    progress?.clear?.();
  }
}

window.notifyAnalysisFetchPlan = notifyAnalysisFetchPlan;
window.notifyAnalysisFetchSummary = notifyAnalysisFetchSummary;
window.runPlaybookAnalysisJob = runPlaybookAnalysisJob;
