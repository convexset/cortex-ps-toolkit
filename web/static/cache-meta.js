/** Format cache age labels for list/analysis toolbars. */

function formatLocalDateTime(isoValue) {
  if (!isoValue) {
    return "";
  }
  const date = new Date(isoValue);
  if (Number.isNaN(date.getTime())) {
    return String(isoValue);
  }
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  });
}

function formatEpochMillis(value, emptyLabel = "—") {
  if (value == null || value === "") {
    return emptyLabel;
  }
  const ms = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(ms) || ms <= 0) {
    return emptyLabel;
  }
  return formatLocalDateTime(new Date(ms).toISOString());
}

function formatCacheMetaLine(data, itemLabel) {
  const count = data.count ?? 0;
  const cache = data.cache || {};
  const refreshedAt = cache.refreshed_at || data.refreshed_at;
  const refreshedLocal = refreshedAt ? formatLocalDateTime(refreshedAt) : "";
  const ageLabel = cache.age_label || (refreshedLocal ? `cached ${refreshedLocal}` : "not loaded yet");
  const stale = cache.stale === true;
  const ttl = data.ttl_seconds ?? cache.ttl_seconds;
  let line = `${count} ${itemLabel}(s) · ${ageLabel}`;
  if (refreshedLocal) {
    line += ` · loaded ${refreshedLocal}`;
  }
  if (typeof ttl === "number") {
    line += ` · TTL ${Math.round(ttl / 60)}m`;
  }
  if (stale) {
    line += " · stale";
  }
  return line;
}

function formatCacheStatusSummary(status) {
  if (!status) return "";
  const parts = ["playbooks", "scripts", "lists"].map((scope) => {
    const item = status[scope];
    if (!item) return null;
    const label = scope.charAt(0).toUpperCase() + scope.slice(1);
    const when = item.refreshed_at
      ? `${item.age_label || "cached"} (${formatLocalDateTime(item.refreshed_at)})`
      : "never";
    const stale = item.stale ? " (stale)" : "";
    return `${label}: ${when}${stale}`;
  }).filter(Boolean);
  const ttl = status.ttl_seconds;
  if (typeof ttl === "number") {
    parts.push(`TTL ${Math.round(ttl / 60)}m`);
  }
  return parts.join(" · ");
}

window.formatLocalDateTime = formatLocalDateTime;
window.formatEpochMillis = formatEpochMillis;
window.formatCacheMetaLine = formatCacheMetaLine;
window.formatCacheStatusSummary = formatCacheStatusSummary;
