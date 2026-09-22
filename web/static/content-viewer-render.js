/** Structured HTML renderers for integration/script content viewer tabs. */

const INTEGRATION_PARAM_TYPES = {
  0: "Short text",
  4: "Encrypted",
  8: "Boolean",
  9: "Credentials",
  12: "Long text",
  13: "Incident type",
  15: "Single select",
  16: "Multi select",
};

function escapeHtml(value) {
  if (typeof window.escapeHtml === "function") return window.escapeHtml(value);
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function truthyFlag(value) {
  return value === true || value === "true";
}

function renderBadge(label, className = "cvr-badge", { title = "" } = {}) {
  if (!label) return "";
  const titleAttr = title ? ` title="${escapeHtml(title)}"` : "";
  return `<span class="${className}"${titleAttr}>${escapeHtml(label)}</span>`;
}

function renderFlagBadges(flags) {
  return flags
    .filter((item) => item.when)
    .map((item) =>
      renderBadge(item.label, `cvr-badge cvr-badge-${item.tone || "muted"}`, {
        title: item.note || item.label,
      }),
    )
    .join("");
}

const COMMAND_FLAG_DEFS = [
  {
    when: (command) => command?.deprecated,
    label: "Deprecated",
    tone: "warn",
    note: "Marked deprecated and may be removed in a future pack or platform version.",
  },
  {
    when: (command) => command?.hidden || command?.docsHidden,
    label: "Hidden",
    tone: "warn",
    note: "Hidden from War Room command search, autocomplete, and docs.",
  },
  {
    when: (command) => command?.sensitive,
    label: "Sensitive",
    tone: "warn",
    note: "Handles sensitive values; output may be redacted in logs and history.",
  },
  {
    when: (command) => command?.polling,
    label: "Polling",
    tone: "muted",
    note: "Uses polling execution; playbooks wait for scheduled follow-up runs.",
  },
  {
    when: (command) => command?.execution === false,
    label: "No execution",
    tone: "muted",
    note: "Does not execute on the integration engine (metadata or display-only).",
  },
];

function commandTimeoutLabel(timeout) {
  if (timeout == null || timeout === "") return "";
  const seconds = Number(timeout);
  if (!Number.isFinite(seconds) || seconds <= 0) return "";
  return `Timeout: ${seconds}s`;
}

function renderCommandFlagMeta(command) {
  const active = COMMAND_FLAG_DEFS.filter((flag) => flag.when(command));
  const timeoutLabel = commandTimeoutLabel(command?.timeout);
  if (!active.length && !timeoutLabel) return "";

  const badges = active
    .map((flag) =>
      renderBadge(flag.label, `cvr-badge cvr-badge-${flag.tone}`, { title: flag.note }),
    )
    .join("");
  const notes = active
    .map((flag) => `<span class="cvr-flag-note">${escapeHtml(flag.note)}</span>`)
    .join("");
  const timeoutHtml = timeoutLabel
    ? `<span class="cvr-meta-inline" title="Maximum runtime allowed for this command, in seconds.">${escapeHtml(timeoutLabel)}</span>`
    : "";

  return `
    <span class="cvr-command-meta">
      <span class="cvr-badge-row cvr-command-badges">${badges}${timeoutHtml ? timeoutHtml : ""}</span>
      ${notes ? `<span class="cvr-command-flag-notes">${notes}</span>` : ""}
    </span>`;
}

function paramTypeLabel(type) {
  const numeric = Number(type);
  if (Number.isFinite(numeric) && INTEGRATION_PARAM_TYPES[numeric]) {
    return INTEGRATION_PARAM_TYPES[numeric];
  }
  if (type) return String(type);
  return "Text";
}

function renderMarkdownish(text) {
  if (!text) return "";
  return escapeHtml(String(text)).replace(/\n/g, "<br />");
}

function renderMarkdown(text) {
  if (!text) return "";
  const raw = String(text);
  if (typeof marked !== "undefined" && typeof marked.parse === "function") {
    try {
      const html = marked.parse(raw, { breaks: true, gfm: true });
      return html.replace(
        /<a href="/g,
        '<a target="_blank" rel="noopener noreferrer" href="',
      );
    } catch (_err) {
      return renderMarkdownish(raw);
    }
  }
  return renderMarkdownish(raw);
}

function renderSelectOptions(options, selectedValue, { disabled = true, prettyMap = null } = {}) {
  if (!Array.isArray(options) || !options.length) return "";
  const selected = selectedValue == null ? "" : String(selectedValue);
  const items = options
    .map((option) => {
      const value = String(option);
      const label = prettyMap && prettyMap[value] != null ? String(prettyMap[value]) : value;
      const isSelected = selected !== "" && selected === value;
      return `<option value="${escapeHtml(value)}"${isSelected ? " selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("");
  return `<select class="cvr-select" ${disabled ? "disabled" : ""} aria-readonly="true">${items}</select>`;
}

function renderIntegrationImage(config) {
  const src = config?.image || config?.icon || "";
  if (!src) return "";
  return `<figure class="cvr-image-wrap"><img class="cvr-image" src="${escapeHtml(src)}" alt="" loading="lazy" /></figure>`;
}

function renderMetaGrid(entries) {
  const visible = entries.filter((entry) => entry.value != null && entry.value !== "");
  if (!visible.length) return "";
  const rows = visible
    .map(
      (entry) =>
        `<div class="cvr-meta-row"><dt>${escapeHtml(entry.label)}</dt><dd>${escapeHtml(String(entry.value))}</dd></div>`,
    )
    .join("");
  return `<dl class="cvr-meta-grid">${rows}</dl>`;
}

function renderReadmeSection(readme, { title = "Documentation" } = {}) {
  if (!readme) return "";
  return `
    <section class="cvr-readme">
      <h4 class="cvr-readme-title">${escapeHtml(title)}</h4>
      <div class="cvr-markdown">${renderMarkdown(readme)}</div>
    </section>`;
}

function renderRawJsonSection(obj, { title = "Raw JSON", hint = "" } = {}) {
  const json = JSON.stringify(obj, null, 2);
  return `
    <details class="analysis-accordion-item cvr-sub-block">
      <summary class="analysis-accordion-summary">${escapeHtml(title)}</summary>
      <div class="analysis-accordion-body">
        ${hint ? `<p class="cvr-raw-hint">${escapeHtml(hint)}</p>` : ""}
        <pre class="cvr-raw-json">${escapeHtml(json)}</pre>
      </div>
    </details>`;
}

function renderRecordOverview(record, { title = "Overview", metaEntries = [], description = "", descriptionTitle = "Description" } = {}) {
  const flags = renderFlagBadges([
    { when: record?.system || record?.isSystemIntegration, label: "System", tone: "system" },
    { when: record?.deprecated, label: "Deprecated", tone: "warn" },
    { when: record?.hidden, label: "Hidden", tone: "warn" },
    { when: truthyFlag(record?.enabled), label: "Enabled", tone: "ok" },
    { when: record?.enabled === "false" || record?.enabled === false, label: "Disabled", tone: "warn" },
    { when: record?.update_available, label: "Update available", tone: "warn" },
    { when: record?.locked, label: "Locked", tone: "warn" },
  ]);
  const meta = renderMetaGrid(metaEntries);
  const summary = description && !String(description).includes("\n##") ? description : "";
  const markdownBody = description && String(description).includes("\n") ? description : "";
  return `
    <section class="cvr-section">
      <header class="cvr-section-header">
        <h3 class="cvr-section-title">${escapeHtml(title)}</h3>
        <div class="cvr-badge-row">${flags}</div>
      </header>
      ${meta}
      ${summary ? `<p class="cvr-summary">${escapeHtml(summary)}</p>` : ""}
      ${markdownBody ? renderReadmeSection(markdownBody, { title: descriptionTitle }) : ""}
    </section>`;
}

function renderScriptOverview(config, title) {
  return renderRecordOverview(config, {
    title: title || config?.name || "Script",
    metaEntries: [
      { label: "ID", value: config?.id || config?.name },
      { label: "Type", value: config?.type || config?.scriptType },
      { label: "Docker", value: config?.dockerImage },
      { label: "Run as", value: config?.runAs },
      { label: "Target", value: config?.scriptTarget },
      { label: "Version", value: config?.version },
    ],
    description: config?.comment || "",
    descriptionTitle: "Comment",
  });
}

function renderScriptArgumentsSection(argumentsList) {
  const args = Array.isArray(argumentsList) ? argumentsList : [];
  if (!args.length) return "";
  const body = args.map((arg) => renderArgumentCard(arg)).join("");
  return `
    <section class="cvr-section">
      <header class="cvr-section-header">
        <h3 class="cvr-section-title">Arguments</h3>
        <span class="cvr-count">${args.length}</span>
      </header>
      <div class="cvr-param-grid">${body}</div>
    </section>`;
}

function renderScriptOutputsSection(outputsList) {
  const outputs = Array.isArray(outputsList) ? outputsList : [];
  if (!outputs.length) return "";
  const body = outputs.map((output) => renderOutputCard(output)).join("");
  return `
    <section class="cvr-section">
      <header class="cvr-section-header">
        <h3 class="cvr-section-title">Context outputs</h3>
        <span class="cvr-count">${outputs.length}</span>
      </header>
      <div class="cvr-param-grid">${body}</div>
    </section>`;
}

function renderListOverview(config, title) {
  return renderRecordOverview(config, {
    title: title || config?.name || "List",
    metaEntries: [
      { label: "ID", value: config?.id || config?.name },
      { label: "Type", value: config?.type },
      { label: "Pack", value: config?.packName || config?.packID },
      { label: "Version", value: config?.version },
    ],
    description: config?.description || "",
  });
}

function renderListDataSection(data, listType) {
  if (data == null || data === "") {
    return `<p class="cvr-empty">List has no data.</p>`;
  }
  const label = listType ? `Data (${listType})` : "Data";
  return `
    <section class="cvr-section">
      <header class="cvr-section-header">
        <h3 class="cvr-section-title">${escapeHtml(label)}</h3>
      </header>
      <pre class="cvr-list-data">${escapeHtml(String(data))}</pre>
    </section>`;
}

function renderTenantCredentialOverview(row) {
  return renderRecordOverview(row, {
    title: row?.name || "Tenant credential",
    metaEntries: [
      { label: "Name", value: row?.name },
      { label: "User", value: row?.user },
      { label: "Workgroup", value: row?.workgroup },
      { label: "Password set", value: row?.has_password ? "Yes" : "No" },
      { label: "Certificate set", value: row?.has_certificate ? "Yes" : "No" },
      { label: "Locked", value: row?.locked ? "Yes" : "No" },
    ],
  });
}

function renderPackOverview(row) {
  return renderRecordOverview(row, {
    title: row?.name || row?.id || "Pack",
    metaEntries: [
      { label: "ID", value: row?.id },
      { label: "Name", value: row?.name },
      { label: "Version", value: row?.current_version },
      { label: "Update available", value: row?.update_available ? "Yes" : "No" },
    ],
  });
}

function renderIntegrationOverview(config, { title = "Overview", extraMeta = [] } = {}) {
  const flags = renderFlagBadges([
    { when: config?.system || config?.isSystemIntegration, label: "System", tone: "system" },
    { when: truthyFlag(config?.hidden), label: "Hidden", tone: "warn" },
    { when: truthyFlag(config?.enabled) || config?.enabled === true, label: "Enabled", tone: "ok" },
    { when: config?.enabled === "false" || config?.enabled === false, label: "Disabled", tone: "warn" },
  ]);
  const summary = config?.description || "";
  const readme = config?.detailedDescription || "";
  const showSummary = Boolean(summary) && summary.trim() !== readme.trim();
  const meta = renderMetaGrid([
    { label: "ID", value: config?.id || config?.name },
    { label: "Display", value: config?.display },
    { label: "Category", value: config?.category },
    { label: "Brand", value: config?.brand },
    { label: "Pack", value: config?.packName || config?.packID },
    { label: "Engine", value: config?.engine },
    ...extraMeta,
  ]);
  return `
    <section class="cvr-section">
      <header class="cvr-section-header">
        <h3 class="cvr-section-title">${escapeHtml(title)}</h3>
        <div class="cvr-badge-row">${flags}</div>
      </header>
      <div class="cvr-overview-layout">
        <div class="cvr-overview-hero">
          ${renderIntegrationImage(config)}
          ${meta}
        </div>
        ${showSummary ? `<p class="cvr-summary">${escapeHtml(summary)}</p>` : ""}
        ${readme ? renderReadmeSection(readme) : !showSummary && summary ? `<p class="cvr-summary">${escapeHtml(summary)}</p>` : ""}
      </div>
    </section>`;
}

function groupParamsBySection(params) {
  const groups = new Map();
  (params || []).forEach((param) => {
    const section = param?.section || "General";
    if (!groups.has(section)) groups.set(section, []);
    groups.get(section).push(param);
  });
  return groups;
}

function renderParamValueControl(param, { showValues = false } = {}) {
  const type = Number(param?.type);
  const options = param?.options || param?.predefined;
  const prettyMap = param?.prettyPredefined;
  const defaultValue = param?.defaultValue;
  const configuredValue = param?.value;
  const value = showValues && configuredValue != null && configuredValue !== "" ? configuredValue : defaultValue;

  if (param?.hiddenPassword || type === 4 || type === 9 || param?.secret) {
    const hasValue = showValues && (param?.hasvalue || configuredValue);
    return `<span class="cvr-value cvr-value-secret">${hasValue ? "••••••••" : "(not set)"}</span>`;
  }
  if (type === 8) {
    const checked = truthyFlag(value);
    return `<label class="cvr-checkbox"><input type="checkbox" disabled ${checked ? "checked" : ""} /> ${checked ? "Yes" : "No"}</label>`;
  }
  if (Array.isArray(options) && options.length) {
    return renderSelectOptions(options, value, { prettyMap });
  }
  if (type === 12) {
    return `<pre class="cvr-inline-pre">${escapeHtml(String(value || ""))}</pre>`;
  }
  if (value == null || value === "") {
    return `<span class="cvr-value cvr-value-empty">${showValues ? "(not set)" : "(no default)"}</span>`;
  }
  return `<span class="cvr-value">${escapeHtml(String(value))}</span>`;
}

function renderParamCard(param, { showValues = false, mode = "definition" } = {}) {
  const name = param?.name || "(unnamed)";
  const display = param?.display || param?.prettyName || name;
  const badges = renderFlagBadges([
    { when: param?.required, label: "Required", tone: "required" },
    { when: param?.advanced, label: "Advanced", tone: "muted" },
    { when: param?.hidden, label: "Hidden", tone: "warn" },
    { when: param?.deprecated, label: "Deprecated", tone: "warn" },
    { when: param?.secret, label: "Secret", tone: "warn" },
  ]);
  const typeLabel = paramTypeLabel(param?.type);
  const autoLabel = param?.auto ? String(param.auto) : "";
  const info = param?.info || param?.description || "";
  const defaultValue = param?.defaultValue;
  const hasPredefined = Array.isArray(param?.predefined) && param.predefined.length;
  const hasOptions = Array.isArray(param?.options) && param.options.length;

  let predefinedBlock = "";
  if (hasPredefined || hasOptions) {
    const options = param.predefined || param.options;
    predefinedBlock = `
      <div class="cvr-field">
        <span class="cvr-field-label">Allowed values</span>
        ${renderSelectOptions(options, showValues ? param?.value : defaultValue, {
          prettyMap: param?.prettyPredefined,
        })}
      </div>`;
  }

  const valueBlock =
    mode === "instance" || showValues
      ? `<div class="cvr-field">
          <span class="cvr-field-label">${mode === "instance" ? "Configured value" : "Default"}</span>
          ${renderParamValueControl(param, { showValues: mode === "instance" })}
        </div>`
      : defaultValue != null && defaultValue !== "" && !hasPredefined && !hasOptions
        ? `<div class="cvr-field">
            <span class="cvr-field-label">Default</span>
            ${renderParamValueControl(param, { showValues: false })}
          </div>`
        : "";

  return `
    <article class="cvr-param-card">
      <header class="cvr-param-header">
        <div>
          <h4 class="cvr-param-title">${escapeHtml(display)}</h4>
          <code class="cvr-param-name">${escapeHtml(name)}</code>
        </div>
        <div class="cvr-badge-row">
          ${renderBadge(typeLabel, "cvr-badge cvr-badge-type")}
          ${autoLabel ? renderBadge(autoLabel, "cvr-badge cvr-badge-muted") : ""}
          ${badges}
        </div>
      </header>
      ${info ? `<div class="cvr-param-desc cvr-markdown">${renderMarkdown(info)}</div>` : ""}
      <div class="cvr-param-fields">
        ${valueBlock}
        ${predefinedBlock}
      </div>
    </article>`;
}

function renderParamSections(params, options = {}) {
  const groups = groupParamsBySection(params);
  if (!groups.size) {
    return `<p class="cvr-empty">No parameters defined.</p>`;
  }
  const sections = [...groups.entries()]
    .map(([section, items]) => {
      const cards = items.map((param) => renderParamCard(param, options)).join("");
      return `
        <details class="analysis-accordion-item cvr-section-block">
          <summary class="analysis-accordion-summary">${escapeHtml(section)} (${items.length})</summary>
          <div class="analysis-accordion-body cvr-param-grid">${cards}</div>
        </details>`;
    })
    .join("");
  return `<div class="analysis-accordion">${sections}</div>`;
}

function renderArgumentCard(arg) {
  const name = arg?.name || "(unnamed)";
  const display = arg?.prettyName || name;
  const badges = renderFlagBadges([
    { when: arg?.required, label: "Required", tone: "required" },
    { when: arg?.secret, label: "Secret", tone: "warn" },
    { when: arg?.hidden, label: "Hidden", tone: "warn" },
    { when: arg?.deprecated, label: "Deprecated", tone: "warn" },
  ]);
  const typeLabel = arg?.type ? String(arg.type) : arg?.auto ? String(arg.auto) : "Argument";
  const defaultBits = [];
  if (arg?.defaultValue != null && arg.defaultValue !== "") defaultBits.push(String(arg.defaultValue));
  if (arg?.default === true) defaultBits.push("(default enabled)");

  let predefinedBlock = "";
  if (Array.isArray(arg?.predefined) && arg.predefined.length) {
    predefinedBlock = `
      <div class="cvr-field">
        <span class="cvr-field-label">Predefined values</span>
        ${renderSelectOptions(arg.predefined, arg.defaultValue, { prettyMap: arg?.prettyPredefined })}
      </div>`;
  }

  return `
    <article class="cvr-param-card cvr-arg-card">
      <header class="cvr-param-header">
        <div>
          <h4 class="cvr-param-title">${escapeHtml(display)}</h4>
          <code class="cvr-param-name">${escapeHtml(name)}</code>
        </div>
        <div class="cvr-badge-row">
          ${renderBadge(typeLabel, "cvr-badge cvr-badge-type")}
          ${badges}
        </div>
      </header>
      ${arg?.description ? `<div class="cvr-param-desc cvr-markdown">${renderMarkdown(arg.description)}</div>` : ""}
      <div class="cvr-param-fields">
        ${
          defaultBits.length
            ? `<div class="cvr-field"><span class="cvr-field-label">Default</span><span class="cvr-value">${escapeHtml(defaultBits.join(" · "))}</span></div>`
            : ""
        }
        ${predefinedBlock}
      </div>
    </article>`;
}

function renderOutputCard(output) {
  const path = output?.contextPath || output?.contentPath || "(no path)";
  return `
    <article class="cvr-param-card cvr-output-card">
      <header class="cvr-param-header">
        <div>
          <h4 class="cvr-param-title"><code class="cvr-path">${escapeHtml(path)}</code></h4>
        </div>
        <div class="cvr-badge-row">
          ${output?.type ? renderBadge(String(output.type), "cvr-badge cvr-badge-type") : ""}
        </div>
      </header>
      ${output?.description ? `<div class="cvr-param-desc cvr-markdown">${renderMarkdown(output.description)}</div>` : ""}
    </article>`;
}

function renderCommandRawSection(command) {
  const json = JSON.stringify(command, null, 2);
  return `
    <details class="analysis-accordion-item cvr-sub-block">
      <summary class="analysis-accordion-summary">Raw JSON</summary>
      <div class="analysis-accordion-body">
        <p class="cvr-raw-hint">JSON as returned by the integration-commands API.</p>
        <pre class="cvr-raw-json">${escapeHtml(json)}</pre>
      </div>
    </details>`;
}

function renderCommandCard(command, index) {
  const name = command?.name || `command-${index + 1}`;
  const display = command?.prettyName || name;
  const args = Array.isArray(command?.arguments) ? command.arguments : [];
  const outputs = Array.isArray(command?.outputs) ? command.outputs : [];
  const flagMeta = renderCommandFlagMeta(command);

  const argsBody = args.length
    ? args.map((arg) => renderArgumentCard(arg)).join("")
    : `<p class="cvr-empty">No arguments.</p>`;
  const outputsBody = outputs.length
    ? outputs.map((output) => renderOutputCard(output)).join("")
    : `<p class="cvr-empty">No context outputs.</p>`;

  return `
    <details class="analysis-accordion-item cvr-command-card" id="cvr-command-${index}">
      <summary class="analysis-accordion-summary cvr-command-summary-row">
        <span class="cvr-command-summary">
          <code class="cvr-command-name">${escapeHtml(name)}</code>
          ${display !== name ? `<span class="cvr-command-display">${escapeHtml(display)}</span>` : ""}
        </span>
        ${flagMeta}
      </summary>
      <div class="analysis-accordion-body">
        ${command?.description ? `<div class="cvr-command-desc cvr-markdown">${renderMarkdown(command.description)}</div>` : ""}
        <details class="analysis-accordion-item cvr-sub-block">
          <summary class="analysis-accordion-summary">Arguments (${args.length})</summary>
          <div class="analysis-accordion-body cvr-param-grid">${argsBody}</div>
        </details>
        <details class="analysis-accordion-item cvr-sub-block">
          <summary class="analysis-accordion-summary">Outputs (${outputs.length})</summary>
          <div class="analysis-accordion-body cvr-param-grid">${outputsBody}</div>
        </details>
        ${renderCommandRawSection(command)}
      </div>
    </details>`;
}

function renderCommandsList(commands) {
  const list = Array.isArray(commands) ? commands : [];
  if (!list.length) {
    return `<p class="cvr-empty">No commands defined.</p>`;
  }
  const cards = list.map((command, index) => renderCommandCard(command, index)).join("");
  return `
    <section class="cvr-section">
      <header class="cvr-section-header">
        <h3 class="cvr-section-title">Commands</h3>
        <span class="cvr-count">${list.length} command${list.length === 1 ? "" : "s"}</span>
      </header>
      <div class="analysis-accordion cvr-command-list">${cards}</div>
    </section>`;
}

function renderDefinitionSettings(configuration) {
  const params = configuration?.configuration;
  if (!Array.isArray(params) || !params.length) {
    return `<p class="cvr-empty">No instance settings defined for this integration.</p>`;
  }
  return `
    <section class="cvr-section">
      <header class="cvr-section-header">
        <h3 class="cvr-section-title">Instance settings</h3>
        <span class="cvr-count">${params.length} parameter${params.length === 1 ? "" : "s"}</span>
      </header>
      ${renderParamSections(params, { mode: "definition" })}
    </section>`;
}

function renderInstanceParameters(parameters) {
  const params = Array.isArray(parameters) ? parameters : [];
  if (!params.length) {
    return `<p class="cvr-empty">No parameters on this instance.</p>`;
  }
  return `
    <section class="cvr-section">
      <header class="cvr-section-header">
        <h3 class="cvr-section-title">Parameter values</h3>
        <span class="cvr-count">${params.length} parameter${params.length === 1 ? "" : "s"}</span>
      </header>
      ${renderParamSections(params, { mode: "instance", showValues: true })}
    </section>`;
}

function contentDetailTabsFromPayload(data) {
  const tabs = [];
  const kind = data?.kind || "";

  if (kind === "integration_definition") {
    tabs.push({
      id: "overview",
      label: "Overview",
      format: "html",
      html: renderIntegrationOverview(data.configuration || {}, { title: data.name || "Integration" }),
      copyText: JSON.stringify(data.configuration, null, 2),
    });
    if (Array.isArray(data.configuration?.configuration) && data.configuration.configuration.length) {
      tabs.push({
        id: "settings",
        label: "Settings",
        format: "html",
        html: renderDefinitionSettings(data.configuration),
        copyText: JSON.stringify(data.configuration.configuration, null, 2),
      });
    }
    if (data.script !== undefined) {
      tabs.push({
        id: "script",
        label: data.script_language ? `Script (${data.script_language})` : "Script",
        content: data.script,
        format: "text",
        emptyMessage: "(no script body)",
      });
    }
    return tabs;
  }

  if (kind === "integration_instance") {
    tabs.push({
      id: "overview",
      label: "Overview",
      format: "html",
      html: renderIntegrationOverview(data.configuration || {}, { title: data.name || "Instance" }),
      copyText: JSON.stringify(data.configuration, null, 2),
    });
    if (data.parameters !== undefined) {
      tabs.push({
        id: "parameters",
        label: "Parameters",
        format: "html",
        html: renderInstanceParameters(data.parameters),
        copyText: JSON.stringify(data.parameters, null, 2),
        emptyMessage: "[]",
      });
    }
    return tabs;
  }

  if (kind === "script") {
    const config = data.configuration || {};
    tabs.push({
      id: "overview",
      label: "Overview",
      format: "html",
      html:
        renderScriptOverview(config, data.name || "Script")
        + renderScriptArgumentsSection(config.arguments)
        + renderScriptOutputsSection(config.outputs)
        + renderRawJsonSection(config),
      copyText: JSON.stringify(config, null, 2),
    });
    if (data.script !== undefined) {
      tabs.push({
        id: "script",
        label: data.script_language ? `Script (${data.script_language})` : "Script",
        content: data.script,
        format: "text",
        emptyMessage: "(no script body)",
      });
    }
    return tabs;
  }

  if (kind === "list") {
    const config = data.configuration || {};
    tabs.push({
      id: "overview",
      label: "Overview",
      format: "html",
      html: renderListOverview(config, data.name || "List") + renderRawJsonSection(config),
      copyText: JSON.stringify(config, null, 2),
    });
    if (data.data !== undefined) {
      tabs.push({
        id: "data",
        label: data.list_type ? `Data (${data.list_type})` : "Data",
        format: "html",
        html: renderListDataSection(data.data, data.list_type),
        copyText: String(data.data ?? ""),
        emptyMessage: "(empty list)",
      });
    }
    return tabs;
  }

  if (kind === "integration_commands") {
    const commandCount = Array.isArray(data.commands) ? data.commands.length : null;
    tabs.push({
      id: "overview",
      label: "Overview",
      format: "html",
      html: renderIntegrationOverview(data.configuration || {}, {
        title: data.name || "Integration",
        extraMeta: commandCount == null ? [] : [{ label: "Commands", value: commandCount }],
      }),
      copyText: JSON.stringify(data.configuration, null, 2),
    });
    if (data.commands !== undefined) {
      tabs.push({
        id: "commands",
        label: "Commands",
        format: "html",
        html: renderCommandsList(data.commands),
        copyText: JSON.stringify(data.commands, null, 2),
        emptyMessage: "[]",
      });
    }
    return tabs;
  }

  if (data.configuration !== undefined) {
    tabs.push({
      id: "configuration",
      label: "Configuration",
      content: JSON.stringify(data.configuration, null, 2),
      format: "json",
      emptyMessage: "{}",
    });
  }
  if (data.script !== undefined) {
    tabs.push({
      id: "script",
      label: data.script_language ? `Script (${data.script_language})` : "Script",
      content: data.script,
      format: "text",
      emptyMessage: "(no script body)",
    });
  }
  if (data.data !== undefined) {
    tabs.push({
      id: "data",
      label: data.list_type ? `Data (${data.list_type})` : "Data",
      content: data.data,
      format: "text",
      emptyMessage: "(empty list)",
    });
  }
  if (data.parameters !== undefined) {
    tabs.push({
      id: "parameters",
      label: "Parameters",
      content: JSON.stringify(data.parameters, null, 2),
      format: "json",
      emptyMessage: "[]",
    });
  }
  if (data.commands !== undefined) {
    tabs.push({
      id: "commands",
      label: "Commands",
      content: JSON.stringify(data.commands, null, 2),
      format: "json",
      emptyMessage: "[]",
    });
  }
  return tabs;
}

window.contentDetailTabsFromPayload = contentDetailTabsFromPayload;
window.renderTenantCredentialOverview = renderTenantCredentialOverview;
window.renderPackOverview = renderPackOverview;
window.renderRawJsonSection = renderRawJsonSection;
