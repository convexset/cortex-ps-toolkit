/** Format cache age labels for list/analysis toolbars. */

const DESIGN_CACHE_LABELS = {
  "incident-types": "Incident types",
  "incident-fields": "Custom fields",
  layouts: "Layouts",
  classifiers: "Classifiers & mappers",
  preprocess: "Pre-process rules",
};

const CORE_CACHE_LABELS = {
  playbooks: "Playbooks",
  scripts: "Scripts",
  lists: "Lists",
};

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

function formatCacheScopeLine(label, item) {
  if (!item) return null;
  const when = item.refreshed_at
    ? `${item.age_label || "cached"} (${formatLocalDateTime(item.refreshed_at)})`
    : "never loaded";
  const stale = item.stale ? " · stale" : "";
  const count = typeof item.count === "number" ? ` · ${item.count} item(s)` : "";
  return `${label}: ${when}${count}${stale}`;
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

function formatDesignContentCachesTooltip(status) {
  if (!status?.design_content) return "";
  return Object.entries(DESIGN_CACHE_LABELS)
    .map(([key, label]) => formatCacheScopeLine(label, status.design_content[key]))
    .filter(Boolean)
    .join("\n");
}

function formatObjectSetupCachesTooltip(status) {
  const lines = formatDesignContentCachesTooltip(status).split("\n").filter(Boolean);
  const correlation = status?.platform_admin?.["correlation-rules"];
  const correlationLine = formatCacheScopeLine("Correlation rules", correlation);
  if (correlationLine) lines.push(correlationLine);
  return lines.join("\n");
}

function formatExtendedCacheTooltip(status) {
  const lines = ["playbooks", "scripts", "lists"]
    .map((scope) => formatCacheScopeLine(CORE_CACHE_LABELS[scope], status?.[scope]))
    .filter(Boolean);
  const design = formatDesignContentCachesTooltip(status);
  if (design) {
    lines.push("", "Design content:", design);
  }
  const correlation = status?.platform_admin?.["correlation-rules"];
  const correlationLine = formatCacheScopeLine("Correlation rules", correlation);
  if (correlationLine) {
    lines.push(correlationLine);
  }
  const ttl = status?.ttl_seconds;
  if (typeof ttl === "number") {
    lines.push("", `Elective TTL threshold: ${Math.round(ttl / 60)}m`);
  }
  return lines.join("\n");
}

function formatCacheStatusSummary(status) {
  if (!status) return "";
  const parts = ["playbooks", "scripts", "lists"].map((scope) => {
    const item = status[scope];
    if (!item) return null;
    const label = CORE_CACHE_LABELS[scope];
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

function renderCacheMetaHtml(line, tooltip) {
  const safeLine = typeof escapeHtml === "function" ? escapeHtml(line) : line;
  const safeTooltip = typeof escapeHtml === "function" ? escapeHtml(tooltip || line) : (tooltip || line);
  return (
    `${safeLine}` +
    ` <button type="button" class="cache-info-btn" title="${safeTooltip}" aria-label="Cache details">ⓘ</button>`
  );
}

function setCacheMetaElement(element, data, itemLabel, { tooltip = "" } = {}) {
  if (!element) return;
  const line = formatCacheMetaLine(data, itemLabel);
  element.innerHTML = renderCacheMetaHtml(line, tooltip || line);
}

window.formatLocalDateTime = formatLocalDateTime;
window.formatEpochMillis = formatEpochMillis;
window.formatCacheScopeLine = formatCacheScopeLine;
window.formatCacheMetaLine = formatCacheMetaLine;
window.formatDesignContentCachesTooltip = formatDesignContentCachesTooltip;
window.formatObjectSetupCachesTooltip = formatObjectSetupCachesTooltip;
window.formatExtendedCacheTooltip = formatExtendedCacheTooltip;
window.formatCacheStatusSummary = formatCacheStatusSummary;
window.renderCacheMetaHtml = renderCacheMetaHtml;
window.setCacheMetaElement = setCacheMetaElement;
