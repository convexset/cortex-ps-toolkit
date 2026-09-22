/** Stale-cache confirmation for cache-only planning (analysis, deep copy, object setup). */

function formatStaleCacheScopeLines(entries) {
  const lines = [
    "Some caches used for this operation are older than the elective TTL threshold:",
    "",
  ];
  for (const entry of entries) {
    const item = entry.item;
    if (!item) continue;
    const profilePrefix = entry.profile ? `${entry.profile} · ` : "";
    const when = item.refreshed_at
      ? `${item.age_label || "cached"} (${formatLocalDateTime(item.refreshed_at)})`
      : "never loaded";
    lines.push(`• ${profilePrefix}${entry.label}: ${when}${item.stale ? " (stale)" : ""}`);
  }
  lines.push(
    "",
    "Cached playbook and script lists are used without refreshing indexes from the tenant.",
    "Individual playbook files needed for analysis are downloaded on demand if missing or outdated.",
  );
  return lines.join("\n");
}

function collectStaleCacheEntries(status, spec) {
  const entries = [];
  const profile = spec.profile || "";
  for (const scope of spec.scopes || []) {
    const item = status?.[scope];
    if (item?.stale) {
      entries.push({
        profile,
        scope,
        label: CORE_CACHE_LABELS?.[scope] || scope,
        item,
      });
    }
  }
  for (const asset of spec.designAssets || []) {
    const item = status?.design_content?.[asset];
    if (item?.stale) {
      entries.push({
        profile,
        scope: asset,
        label: DESIGN_CACHE_LABELS?.[asset] || asset,
        item,
      });
    }
  }
  return entries;
}

async function fetchCacheStatus(profile) {
  return api(`/api/cache/status?profile=${encodeURIComponent(profile)}`);
}

async function refreshCacheScopes(profile, scopes = [], designAssets = [], options = {}) {
  const useLoader = options.useLoader !== false;
  const progress = options.progress;
  const uniqueScopes = [...new Set(scopes)];
  const uniqueAssets = [...new Set(designAssets)];

  const run = async () => {
    if (window.cptkWs?.isConnected?.()) {
      for (const scope of uniqueScopes) {
        const label = `Refreshing ${CORE_CACHE_LABELS?.[scope] || scope} (${profile})…`;
        progress?.show?.(label);
        await window.cptkWs.submitJob(
          "cache.refresh",
          { profile, scope },
          progress?.wsJobOptions?.({ startMessage: label }) || {},
        );
      }
      for (const asset of uniqueAssets) {
        const label = `Refreshing ${DESIGN_CACHE_LABELS?.[asset] || asset} (${profile})…`;
        progress?.show?.(label);
        await window.cptkWs.submitJob(
          "cache.refresh",
          { profile, scope: "design_content", asset },
          progress?.wsJobOptions?.({ startMessage: label }) || {},
        );
      }
      return;
    }
    for (const scope of uniqueScopes) {
      if (scope === "playbooks") {
        await api("/api/playbooks/refresh", { method: "POST", body: JSON.stringify({ profile }) });
      } else if (scope === "scripts") {
        await api("/api/scripts/refresh", { method: "POST", body: JSON.stringify({ profile }) });
      } else if (scope === "lists") {
        await api("/api/lists/refresh", { method: "POST", body: JSON.stringify({ profile }) });
      }
    }
    for (const asset of uniqueAssets) {
      await api(`/api/design-content/${encodeURIComponent(asset)}/refresh`, {
        method: "POST",
        body: JSON.stringify({ profile }),
      });
    }
  };

  if (!useLoader) {
    return run();
  }
  const scopeLabels = uniqueScopes.map((scope) => CORE_CACHE_LABELS?.[scope] || scope);
  const assetLabels = uniqueAssets.map((asset) => DESIGN_CACHE_LABELS?.[asset] || asset);
  const label = [...scopeLabels, ...assetLabels].join(", ") || "caches";
  return withLoader(run, `Refreshing ${label} (${profile})…`);
}

function buildStaleCacheRefreshPlan(staleEntries, specs) {
  const refreshByProfile = new Map();
  for (const entry of staleEntries) {
    const bucket = refreshByProfile.get(entry.profile) || { scopes: new Set(), designAssets: new Set() };
    if (entry.scope && specs.some((spec) => spec.designAssets?.includes(entry.scope))) {
      bucket.designAssets.add(entry.scope);
    } else {
      bucket.scopes.add(entry.scope);
    }
    refreshByProfile.set(entry.profile, bucket);
  }
  return refreshByProfile;
}

async function runStaleCacheRefreshPlan(refreshByProfile, options = {}) {
  for (const [profile, bucket] of refreshByProfile.entries()) {
    await refreshCacheScopes(profile, [...bucket.scopes], [...bucket.designAssets], {
      useLoader: options.useLoader,
      progress: options.progress,
    });
  }
}

/**
 * @param {{profile: string, scopes?: string[], designAssets?: string[]}[]} profileSpecs
 * @param {{ deferRefresh?: boolean, refreshMessage?: string }} [options]
 * @returns {Promise<"cancel"|"proceed"|"refreshed"|{ action: "refresh", runRefresh: () => Promise<void> }>}
 */
async function promptStaleCacheChoice(profileSpecs, options = {}) {
  const deferRefresh = options.deferRefresh === true;
  const specs = profileSpecs.filter((spec) => spec?.profile);
  if (!specs.length) {
    return "proceed";
  }
  const statuses = await Promise.all(specs.map((spec) => fetchCacheStatus(spec.profile)));
  const staleEntries = [];
  specs.forEach((spec, index) => {
    staleEntries.push(...collectStaleCacheEntries(statuses[index], spec));
  });
  if (!staleEntries.length) {
    return "proceed";
  }
  const choice = await showChoiceDialog({
    title: "Stale cache",
    message: formatStaleCacheScopeLines(staleEntries),
    primaryLabel: "Refresh caches and proceed",
    secondaryLabel: "Proceed with current cache",
    cancelLabel: "Cancel",
  });
  if (!choice) {
    return "cancel";
  }
  if (choice === "primary") {
    const refreshByProfile = buildStaleCacheRefreshPlan(staleEntries, specs);
    const runRefresh = () => runStaleCacheRefreshPlan(refreshByProfile, { useLoader: false });
    if (deferRefresh) {
      const refreshByProfile = buildStaleCacheRefreshPlan(staleEntries, specs);
      return { action: "refresh", runRefresh, refreshByProfile };
    }
    await withLoader(runRefresh, options.refreshMessage || "Refreshing caches…");
    return "refreshed";
  }
  return "proceed";
}

async function runStaleCacheRefreshWithProgress(refreshByProfile, progress, options = {}) {
  if (!refreshByProfile?.size) {
    return;
  }
  await runStaleCacheRefreshPlan(refreshByProfile, { useLoader: false, progress, ...options });
}

window.promptStaleCacheChoice = promptStaleCacheChoice;
window.refreshCacheScopes = refreshCacheScopes;
window.runStaleCacheRefreshWithProgress = runStaleCacheRefreshWithProgress;
window.buildStaleCacheRefreshPlan = buildStaleCacheRefreshPlan;
