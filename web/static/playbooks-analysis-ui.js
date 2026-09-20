/** Playbook analysis accordion: one collapsible panel per analysis run. */

let analysisCounter = 0;

function initPlaybooksAnalysisPanel() {
  document.getElementById("playbooks-analyze")?.addEventListener("click", analyzeSelectedPlaybook);
}

function selectedPlaybookRows() {
  if (window.playbooksTools?.getSelectedRows) {
    return window.playbooksTools.getSelectedRows();
  }
  const table = window.playbooksTools?.table;
  if (!table) return [];
  return table.getSelectedData();
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderAnalysisTableHtml(headers, rows) {
  const head = headers.map((h) => `<th>${escapeHtml(h)}</th>`).join("");
  const body = rows.length
    ? rows
        .map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(String(cell))}</td>`).join("")}</tr>`)
        .join("")
    : `<tr><td colspan="${headers.length}">None</td></tr>`;
  return `<table class="analysis-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderTooltipCell(label, tooltip) {
  const text = escapeHtml(String(label));
  if (!tooltip || tooltip === label) {
    return text;
  }
  return `<span class="analysis-tooltip" title="${escapeHtml(String(tooltip))}">${text}</span>`;
}

function analysisHelpButton(summary, detailHtml = "") {
  const short = escapeHtml(String(summary || ""));
  const detail = detailHtml ? `<span class="analysis-help-detail hidden">${detailHtml}</span>` : "";
  return (
    `<span class="analysis-help-wrap">` +
    `<button type="button" class="analysis-help-btn" aria-label="Help" title="${short}">?</button>` +
    detail +
    `</span>`
  );
}

function bindAnalysisHelp(root) {
  root?.querySelectorAll(".analysis-help-btn").forEach((button) => {
    if (button.dataset.helpBound) {
      return;
    }
    button.dataset.helpBound = "1";
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const detail = button.parentElement?.querySelector(".analysis-help-detail");
      if (detail) {
        detail.classList.toggle("hidden");
        return;
      }
      const title = button.getAttribute("title");
      if (title && typeof showOutcomeDialog === "function") {
        showOutcomeDialog({ title: "Help", message: title, success: true });
      }
    });
  });
}

function bindAnalysisSectionNav(root, panelKey) {
  root?.querySelectorAll(".analysis-section-nav a").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const href = link.getAttribute("href") || "";
      const target = root.querySelector(href) || document.getElementById(href.replace(/^#/, ""));
      target?.scrollIntoView({ behavior: "smooth", block: "start" });
      root.querySelectorAll(".analysis-section-nav a").forEach((item) => {
        item.classList.toggle("active", item === link);
      });
    });
  });

  root?.querySelectorAll(".analysis-task-tab").forEach((button) => {
    button.addEventListener("click", () => {
      const tab = button.dataset.taskTab;
      root.querySelectorAll(".analysis-task-tab").forEach((item) => {
        item.classList.toggle("active", item === button);
        item.setAttribute("aria-pressed", item === button ? "true" : "false");
      });
      root.querySelectorAll(".analysis-task-panel").forEach((panel) => {
        panel.classList.toggle("hidden", panel.dataset.taskTab !== tab);
      });
    });
  });
}

function buildCommandsTableHtml(commands) {
  const rows = (commands || [])
    .map(
      (row) =>
        `<tr>` +
        `<td>${renderTooltipCell(row.command, row.raw)}</td>` +
        `<td>${escapeHtml(String(row.count))}</td>` +
        `</tr>`,
    )
    .join("");
  return (
    `<table class="analysis-table"><thead><tr><th>Command</th><th>Count</th></tr></thead>` +
    `<tbody>${rows || '<tr><td colspan="2">None</td></tr>'}</tbody></table>`
  );
}

function formatTaskListingMetric(value) {
  return value == null || value === "" ? "—" : String(value);
}

function flowGraphIndexForPlaybook(data, playbookId) {
  const graphs = data?.flow_graphs || [];
  const index = graphs.findIndex((entry) => String(entry.playbook_id) === String(playbookId));
  return index >= 0 ? index : 0;
}

const PLAYBOOK_TASK_LISTING_HEADERS = [
  "Task #",
  "Title",
  "Type",
  "Scripts",
  "Playbooks",
  "Commands",
  "Reachable",
  "Min from start",
  "Max from start",
  "Min to terminal",
  "Max to terminal",
  "Conditional branches",
];

function playbookTaskListingRowHtml(data, pb, task) {
  const flowIndex = flowGraphIndexForPlaybook(data, pb.playbook_id);
  return [
    `<button type="button" class="playbook-task-focus-link" data-flow-index="${flowIndex}" data-task-id="${escapeHtml(task.task_id)}" title="Show in flow graph">#${escapeHtml(task.task_id)}</button>`,
    escapeHtml(task.title || "—"),
    escapeHtml(task.task_type || "—"),
    escapeHtml(formatTaskSummaryList(task.scripts)),
    escapeHtml(formatTaskSummaryList(task.playbooks)),
    escapeHtml(formatTaskSummaryList(task.commands)),
    task.expanded_reachable ? "Yes" : "No",
    formatTaskListingMetric(task.min_steps_from_start),
    formatTaskListingMetric(task.max_steps_from_start),
    formatTaskListingMetric(task.min_steps_to_terminal),
    formatTaskListingMetric(task.max_steps_to_terminal),
    escapeHtml(formatTaskSummaryList(task.conditional_branches)),
  ];
}

function buildPlaybookTaskListingsHtml(data) {
  return (data.playbook_task_listings || [])
    .map((pb) => {
      const rows = (pb.tasks || []).map((task) => playbookTaskListingRowHtml(data, pb, task));
      const role = pb.role ? ` · ${escapeHtml(pb.role)}` : "";
      return (
        `<div class="playbook-task-listing">` +
        `<h4>${escapeHtml(pb.playbook_name || pb.playbook_id)}${role}</h4>` +
        renderAnalysisTableHtml(PLAYBOOK_TASK_LISTING_HEADERS, rows) +
        `</div>`
      );
    })
    .join("");
}

function bindPlaybookTaskListingLinks(details, panelKey) {
  details.querySelectorAll(".playbook-task-focus-link").forEach((button) => {
    button.addEventListener("click", () => {
      const flowIndex = Number(button.dataset.flowIndex);
      const taskId = button.dataset.taskId;
      const hostId = `flow-graph-host-${panelKey}`;
      const host = document.getElementById(hostId);
      if (host && taskId) {
        host.dataset.selectedTaskId = String(taskId);
      }
      if (Number.isFinite(flowIndex) && details._selectFlowTask) {
        details._selectFlowTask(taskId, flowIndex);
      } else if (details._selectFlowTask) {
        details._selectFlowTask(taskId);
      }
      document.getElementById(`section-flow-${panelKey}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

let flowGraphMermaidInitialized = false;
const FLOW_GRAPH_MERMAID_THEME = {
  primaryColor: "#1e2936",
  primaryTextColor: "#e6edf3",
  primaryBorderColor: "#2d3a47",
  lineColor: "#6b8cae",
  tertiaryColor: "#152028",
  fontSize: "15px",
  fontFamily: "ui-sans-serif, system-ui, sans-serif",
};

function ensureFlowGraphMermaidReady() {
  if (typeof mermaid === "undefined") {
    return false;
  }
  if (!flowGraphMermaidInitialized) {
    mermaid.initialize({
      startOnLoad: false,
      theme: "dark",
      flowchart: {
        curve: "basis",
        padding: 24,
        nodeSpacing: 60,
        rankSpacing: 80,
        useMaxWidth: false,
        htmlLabels: false,
      },
      themeVariables: FLOW_GRAPH_MERMAID_THEME,
    });
    flowGraphMermaidInitialized = true;
  }
  return true;
}

function escapeMermaidLabel(text) {
  return String(text)
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/\[/g, "#91;")
    .replace(/\]/g, "#93;")
    .replace(/[<>]/g, " ")
    .replace(/\n/g, " ");
}

function structureTreePlaybookName(line, lineIndex) {
  const trimmed = String(line).trim();
  if (lineIndex === 0) {
    return trimmed || null;
  }
  if (trimmed.includes("circular reference skipped")) {
    return null;
  }
  const match = trimmed.match(/^\+-\s*(.+?)(\s+\(\d+x\))?(\s+\[MISSING\])?$/);
  return match ? match[1].trim() : null;
}

function buildStructureTreeLineHtml(line, lineIndex, flowGraphs) {
  const playbookName = structureTreePlaybookName(line, lineIndex);
  const flowIndex =
    playbookName != null
      ? (flowGraphs || []).findIndex((entry) => entry.playbook_name === playbookName)
      : -1;
  const indent = String(line).match(/^(\s*)/)?.[1]?.replace(/ /g, "\u00a0") || "";
  if (lineIndex === 0) {
    const label =
      flowIndex >= 0
        ? `<button type="button" class="structure-tree-link" data-flow-index="${flowIndex}">${escapeHtml(playbookName)}</button>`
        : escapeHtml(line);
    return `<div class="structure-tree-line">${label}</div>`;
  }
  if (!playbookName) {
    return `<div class="structure-tree-line">${escapeHtml(line)}</div>`;
  }
  const suffix = String(line).trim().slice(String(line).trim().indexOf(playbookName) + playbookName.length);
  const link =
    flowIndex >= 0
      ? `<button type="button" class="structure-tree-link" data-flow-index="${flowIndex}">${escapeHtml(playbookName)}</button>`
      : escapeHtml(playbookName);
  return `<div class="structure-tree-line">${indent}+- ${link}${escapeHtml(suffix)}</div>`;
}

function buildStructureSectionHtml(data, panelKey) {
  const treeLines = data.structure_tree || [];
  const flowGraphs = data.flow_graphs || [];
  const treeHtml = treeLines
    .map((line, index) => buildStructureTreeLineHtml(line, index, flowGraphs))
    .join("");
  return `
    <div class="structure-section" data-panel-key="${escapeHtml(panelKey)}">
      <h3>Playbook structure ${analysisHelpButton(
        "Nesting of sub-playbook calls in the expanded tree.",
        "<p>Click a playbook name to jump to its <strong>Flow</strong> tab. Counts like <code>(2x)</code> mean the sub-playbook is invoked from multiple places.</p>",
      )}</h3>
      <p class="meta">Sub-playbook nesting. Click a name to open its flow graph tab.</p>
      ${
        treeLines.length
          ? `<div class="structure-tree">${treeHtml}</div>`
          : `<p class="meta">Structure tree unavailable.</p>`
      }
    </div>
  `;
}

function flowNodeMermaidId(taskId) {
  return `t${String(taskId).replace(/[^a-zA-Z0-9_]/g, "_")}`;
}

function flowNodeDisplayText(node) {
  if (node.task_type === "start" || node.is_start) {
    return `#${node.id}\nSTART`;
  }
  const title = node.label || node.id;
  const subtitle = node.detail ? `\n${node.detail}` : "";
  return `#${node.id} · ${title}${subtitle}`;
}

function flowNodeMermaidShape(node) {
  const text = escapeMermaidLabel(flowNodeDisplayText(node));
  const nodeId = flowNodeMermaidId(node.id);
  if (node.task_type === "start" || node.is_start) {
    return `${nodeId}(("${text}"))`;
  }
  switch (node.task_type) {
    case "playbook":
      return `${nodeId}[["${text}"]]`;
    case "condition":
    case "conditionals":
      return `${nodeId}{"${text}"}`;
    case "title":
      return `${nodeId}(["${text}"])`;
    default:
      return `${nodeId}["${text}"]`;
  }
}

function filterFlowGraph(graph, { hideUnreachable = false } = {}) {
  if (!hideUnreachable) {
    return graph;
  }
  const nodes = (graph?.nodes || []).filter((node) => node.reachable);
  const visible = new Set(nodes.map((node) => node.id));
  const edges = (graph?.edges || []).filter((edge) => visible.has(edge.from) && visible.has(edge.to));
  return { ...graph, nodes, edges };
}

function flowGraphDirection(graph, preferred) {
  if (preferred === "LR" || preferred === "TD") {
    return preferred;
  }
  return (graph?.nodes || []).length > 14 ? "TD" : "LR";
}

function appendFlowNodeClass(classLines, node) {
  if (!node.reachable) {
    classLines.push(`class ${flowNodeMermaidId(node.id)} flowUnreachable`);
    return;
  }
  if (node.task_type === "start" || node.is_start) {
    classLines.push(`class ${flowNodeMermaidId(node.id)} flowTypestart`);
    return;
  }
  const className = `flowType${String(node.task_type || "unknown").replace(/[^a-zA-Z0-9]/g, "")}`;
  classLines.push(`class ${flowNodeMermaidId(node.id)} ${className}`);
}

function appendFlowEdgeLine(lines, edge, indent = "") {
  const fromId = flowNodeMermaidId(edge.from);
  const toId = flowNodeMermaidId(edge.to);
  const condition = String(edge.condition || "").trim();
  const link = condition ? `-->|"${escapeMermaidLabel(condition)}"|` : "-->";
  lines.push(`${indent}${fromId} ${link} ${toId}`);
}

function appendFlowMermaidClassDefs(lines) {
  lines.push("classDef flowUnreachable fill:#1a1f24,stroke:#4a5560,color:#8b949e,stroke-dasharray:4 2");
  lines.push("classDef flowTypestart fill:#1e3a2f,stroke:#7dd3a8,color:#e6edf3");
  lines.push("classDef flowTypeplaybook fill:#1e2936,stroke:#6b8cae,color:#e6edf3");
  lines.push("classDef flowTypecondition fill:#3d2e14,stroke:#d4a24c,color:#ffe8b3");
  lines.push("classDef flowTypeconditionals fill:#3d2e14,stroke:#d4a24c,color:#ffe8b3");
  lines.push("classDef flowTypetitle fill:#152028,stroke:#2d3a47,color:#c9d1d9");
  lines.push("classDef flowTyperegular fill:#1e2936,stroke:#2d3a47,color:#e6edf3");
}

function buildFlowMermaidSource(graph, { direction: preferredDirection = null } = {}) {
  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];
  if (!nodes.length) {
    return "";
  }

  const direction = flowGraphDirection(graph, preferredDirection);
  const lines = [];
  const classLines = [];
  const reachableNodes = nodes.filter((node) => node.reachable !== false);
  const unreachableNodes = nodes.filter((node) => node.reachable === false);
  const useSplitLayout = reachableNodes.length > 0 && unreachableNodes.length > 0;
  const reachableIds = new Set(reachableNodes.map((node) => node.id));
  const unreachableIds = new Set(unreachableNodes.map((node) => node.id));

  if (!useSplitLayout) {
    lines.push(`flowchart ${direction}`);
    for (const node of nodes) {
      lines.push(`  ${flowNodeMermaidShape(node)}`);
      appendFlowNodeClass(classLines, node);
    }
    for (const edge of edges) {
      appendFlowEdgeLine(lines, edge, "  ");
    }
    appendFlowMermaidClassDefs(lines);
    lines.push(...classLines);
    return lines.join("\n");
  }

  const outerDirection = direction === "LR" ? "TB" : "LR";
  const innerDirection = direction;
  lines.push(`flowchart ${outerDirection}`);
  lines.push('  subgraph flowReachable[" "]');
  lines.push(`    direction ${innerDirection}`);
  for (const node of reachableNodes) {
    lines.push(`    ${flowNodeMermaidShape(node)}`);
    appendFlowNodeClass(classLines, node);
  }
  for (const edge of edges) {
    if (reachableIds.has(edge.from) && reachableIds.has(edge.to)) {
      appendFlowEdgeLine(lines, edge, "    ");
    }
  }
  lines.push("  end");
  lines.push('  subgraph flowUnreachable["Unreachable"]');
  lines.push(`    direction ${innerDirection}`);
  for (const node of unreachableNodes) {
    lines.push(`    ${flowNodeMermaidShape(node)}`);
    appendFlowNodeClass(classLines, node);
  }
  for (const edge of edges) {
    if (unreachableIds.has(edge.from) && unreachableIds.has(edge.to)) {
      appendFlowEdgeLine(lines, edge, "    ");
    }
  }
  lines.push("  end");
  lines.push("  flowReachable ~~~ flowUnreachable");
  for (const edge of edges) {
    const fromReachable = reachableIds.has(edge.from);
    const toReachable = reachableIds.has(edge.to);
    if (fromReachable !== toReachable) {
      appendFlowEdgeLine(lines, edge, "  ");
    }
  }
  appendFlowMermaidClassDefs(lines);
  lines.push(...classLines);
  return lines.join("\n");
}

const FLOW_SAVED_BASE = { width: 200, height: 76, font: 12, pad: 10, gap: 48 };
const FLOW_SAVED_SCALE_DEFAULT = 1.5;
const FLOW_SAVED_SCALE_MIN = 1;
const FLOW_SAVED_SCALE_MAX = 2;
const FLOW_SAVED_NODE_MAX_LINES = 4;

function flowSavedNodeScale(viewState) {
  const raw = Number(viewState?.savedNodeScale ?? FLOW_SAVED_SCALE_DEFAULT);
  if (!Number.isFinite(raw)) {
    return FLOW_SAVED_SCALE_DEFAULT;
  }
  return Math.min(FLOW_SAVED_SCALE_MAX, Math.max(FLOW_SAVED_SCALE_MIN, raw));
}

function flowSavedMetrics(viewState) {
  const scale = flowSavedNodeScale(viewState);
  return {
    scale,
    width: Math.round(FLOW_SAVED_BASE.width * scale),
    height: Math.round(FLOW_SAVED_BASE.height * scale),
    fontSize: Math.round(FLOW_SAVED_BASE.font * scale),
    pad: Math.max(8, Math.round(FLOW_SAVED_BASE.pad * scale)),
    gap: Math.round(FLOW_SAVED_BASE.gap * scale),
    edgeFontSize: Math.round(FLOW_SAVED_BASE.font * scale),
  };
}

function flowGraphUsesSavedView(viewState) {
  return viewState?.useSavedViewPlacement !== false;
}

function parseTaskViewPosition(rawTask) {
  if (!rawTask) {
    return null;
  }
  let view = rawTask.view;
  if (view == null) {
    return null;
  }
  if (typeof view === "string") {
    try {
      view = JSON.parse(view);
    } catch {
      return null;
    }
  }
  const x = Number(view?.position?.x);
  const y = Number(view?.position?.y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    return null;
  }
  return { x, y };
}

function graphHasSavedViewPositions(graph) {
  return (graph?.nodes || []).some((node) => parseTaskViewPosition(node.raw_task));
}

function flowSavedNodeClass(node) {
  if (!node.reachable) {
    return "flowUnreachable";
  }
  if (node.task_type === "start" || node.is_start) {
    return "flowTypestart";
  }
  return `flowType${String(node.task_type || "unknown").replace(/[^a-zA-Z0-9]/g, "")}`;
}

function flowSavedApproxCharsPerLine(innerWidth, fontSize) {
  return Math.max(8, Math.floor((innerWidth - 4) / (fontSize * 0.52)));
}

function flowSavedWrapText(text, maxChars, maxLines = FLOW_SAVED_NODE_MAX_LINES) {
  const words = String(text).split(/\s+/).filter(Boolean);
  if (!words.length) {
    return [""];
  }
  const lines = [];
  let current = "";
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length <= maxChars) {
      current = candidate;
      continue;
    }
    if (current) {
      lines.push(current);
      current = word;
    } else {
      lines.push(`${word.slice(0, Math.max(1, maxChars - 1))}…`);
      current = "";
    }
    if (lines.length >= maxLines) {
      break;
    }
  }
  if (current && lines.length < maxLines) {
    lines.push(current);
  }
  if (lines.length > maxLines) {
    lines.length = maxLines;
  }
  if (lines.length === maxLines) {
    const last = lines[maxLines - 1];
    if (last.length > maxChars) {
      lines[maxLines - 1] = `${last.slice(0, Math.max(1, maxChars - 1))}…`;
    } else if (words.join(" ").length > lines.join(" ").length) {
      lines[maxLines - 1] = `${last.replace(/…$/, "")}…`;
    }
  }
  return lines.length ? lines : [String(text).slice(0, maxChars)];
}

function flowSavedNodeLabelLines(node, innerWidth, isCondition = false, fontSize = 18) {
  const effectiveWidth = innerWidth * (isCondition ? 0.58 : 1);
  const maxChars = flowSavedApproxCharsPerLine(effectiveWidth, fontSize);
  if (node.task_type === "start" || node.is_start) {
    return flowSavedWrapText(`#${node.id} START`, maxChars, 2);
  }
  const title = String(node.label || node.id);
  const primary = `#${node.id} · ${title}`;
  const lines = flowSavedWrapText(primary, maxChars, isCondition ? 2 : 3);
  if (node.detail && node.detail !== title && lines.length < FLOW_SAVED_NODE_MAX_LINES) {
    const detailLines = flowSavedWrapText(
      String(node.detail),
      maxChars,
      FLOW_SAVED_NODE_MAX_LINES - lines.length,
    );
    lines.push(...detailLines);
  }
  return lines.slice(0, FLOW_SAVED_NODE_MAX_LINES);
}

function flowSavedNodeLabelHtml(node, innerWidth, innerHeight, isCondition = false, fontSize = 18) {
  const lines = flowSavedNodeLabelLines(node, innerWidth, isCondition, fontSize);
  return lines
    .map((line) => `<div class="flow-saved-node-line">${escapeHtml(line)}</div>`)
    .join("");
}

function buildFlowSavedViewLayouts(graph, metrics) {
  const nodes = graph?.nodes || [];
  const layouts = {};
  for (const node of nodes) {
    const pos = parseTaskViewPosition(node.raw_task);
    if (pos) {
      layouts[node.id] = pos;
    }
  }
  if (!Object.keys(layouts).length) {
    return null;
  }
  let maxX = Math.max(...Object.values(layouts).map((pos) => pos.x));
  const minY = Math.min(...Object.values(layouts).map((pos) => pos.y));
  for (const node of nodes) {
    if (layouts[node.id]) {
      continue;
    }
    maxX += metrics.width + metrics.gap;
    layouts[node.id] = { x: maxX, y: minY };
  }
  return layouts;
}

function flowSavedNodeAnchor(layouts, taskId, side, metrics) {
  const pos = layouts[taskId];
  if (!pos) {
    return { x: 0, y: 0 };
  }
  if (side === "bottom") {
    return { x: pos.x + metrics.width / 2, y: pos.y + metrics.height };
  }
  if (side === "top") {
    return { x: pos.x + metrics.width / 2, y: pos.y };
  }
  return { x: pos.x + metrics.width / 2, y: pos.y + metrics.height / 2 };
}

function buildFlowSavedViewSvg(graph, viewState) {
  const metrics = flowSavedMetrics(viewState);
  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];
  const layouts = buildFlowSavedViewLayouts(graph, metrics);
  if (!layouts) {
    return null;
  }

  const parts = ['<svg xmlns="http://www.w3.org/2000/svg"><g class="root">'];
  parts.push(`<style>.flow-edges .flow-edge-label{font-size:${metrics.edgeFontSize}px;}</style>`);
  parts.push('<g class="flow-edges">');
  for (const edge of edges) {
    if (!layouts[edge.from] || !layouts[edge.to]) {
      continue;
    }
    const from = flowSavedNodeAnchor(layouts, edge.from, "bottom", metrics);
    const to = flowSavedNodeAnchor(layouts, edge.to, "top", metrics);
    const midY = (from.y + to.y) / 2;
    const condition = String(edge.condition || "").trim();
    parts.push(
      `<path class="flow-edge" d="M ${from.x} ${from.y} C ${from.x} ${midY}, ${to.x} ${midY}, ${to.x} ${to.y}" fill="none" />`,
    );
    if (condition) {
      parts.push(
        `<text class="flow-edge-label" x="${(from.x + to.x) / 2}" y="${midY - 8}" text-anchor="middle">${escapeHtml(condition)}</text>`,
      );
    }
  }
  parts.push('<defs>');
  for (const node of nodes) {
    const clipId = `flow-clip-${flowNodeMermaidId(node.id)}`;
    parts.push(
      `<clipPath id="${clipId}"><rect x="0" y="0" width="${metrics.width}" height="${metrics.height}" rx="6" ry="6" /></clipPath>`,
    );
  }
  parts.push("</defs></g><g class=\"flow-nodes\">");
  for (const node of nodes) {
    const pos = layouts[node.id];
    const cls = flowSavedNodeClass(node);
    const isCondition = node.task_type === "condition" || node.task_type === "conditionals";
    const pad = isCondition ? Math.round(metrics.pad * 1.4) : metrics.pad;
    const innerWidth = metrics.width - pad * 2;
    const innerHeight = metrics.height - pad * 2;
    const clipId = `flow-clip-${flowNodeMermaidId(node.id)}`;
    parts.push(
      `<g class="node flow-saved-node ${cls}" data-task-id="${escapeHtml(node.id)}" transform="translate(${pos.x}, ${pos.y})" clip-path="url(#${clipId})">`,
    );
    if (node.task_type === "start" || node.is_start) {
      parts.push(
        `<rect class="flow-node-shape" x="0" y="0" width="${metrics.width}" height="${metrics.height}" rx="${metrics.height / 2}" ry="${metrics.height / 2}" />`,
      );
    } else if (isCondition) {
      const cx = metrics.width / 2;
      const cy = metrics.height / 2;
      parts.push(
        `<polygon class="flow-node-shape" points="${cx},0 ${metrics.width},${cy} ${cx},${metrics.height} 0,${cy}" />`,
      );
    } else {
      parts.push(
        `<rect class="flow-node-shape" x="0" y="0" width="${metrics.width}" height="${metrics.height}" rx="6" ry="6" />`,
      );
    }
    parts.push(
      `<foreignObject x="${pad}" y="${pad}" width="${innerWidth}" height="${innerHeight}">` +
        `<div xmlns="http://www.w3.org/1999/xhtml" class="flow-saved-node-text" style="font-size:${metrics.fontSize}px">` +
        `${flowSavedNodeLabelHtml(node, innerWidth, innerHeight, isCondition, metrics.fontSize)}` +
        `</div></foreignObject>`,
    );
    parts.push("</g>");
  }
  parts.push("</g></g></svg>");
  return parts.join("");
}

function mountFlowSavedViewSvg(host, graph, viewState) {
  const stage = host.querySelector(".flow-graph-stage");
  const markup = buildFlowSavedViewSvg(graph, viewState);
  if (!stage || !markup) {
    return false;
  }
  stage.innerHTML = markup;
  return true;
}

function syncFlowGraphLayoutControls(host, viewState) {
  const useSaved = flowGraphUsesSavedView(viewState);
  const savedToggle = host.querySelector(".flow-graph-saved-view");
  if (savedToggle) {
    savedToggle.checked = useSaved;
  }
  const scaleInput = host.querySelector(".flow-graph-saved-scale");
  if (scaleInput) {
    scaleInput.value = String(flowSavedNodeScale(viewState));
    scaleInput.disabled = !useSaved;
  }
  host.querySelector(".flow-graph-scale")?.classList.toggle("hidden", !useSaved);
  host.querySelector(".flow-graph-toolbar")?.classList.toggle("flow-graph-saved-layout", useSaved);
  host.querySelectorAll(".flow-graph-layout").forEach((button) => {
    button.disabled = useSaved;
    button.title = useSaved
      ? "Layout controls apply only when saved view placement is off"
      : button.dataset.direction === "LR"
        ? "Layout: flow runs left to right (horizontal)"
        : "Layout: flow runs top to bottom (vertical)";
  });
}

function buildFlowGraphsSectionHtml(data, panelKey) {
  const flowGraphs = data.flow_graphs || [];
  if (!flowGraphs.length) {
    return `<section class="flow-graphs-section"><h3>Playbook flows</h3><p class="meta">Flow graphs unavailable.</p></section>`;
  }

  const nav = flowGraphs
    .map((entry, index) => {
      const role = entry.role === "root" ? "root" : "sub";
      const label = `${entry.playbook_name} (${role})`;
      const active = index === 0 ? " active" : "";
      return (
        `<button type="button" class="flow-graph-tab${active}" ` +
        `data-flow-index="${index}" aria-pressed="${index === 0 ? "true" : "false"}">` +
        `${escapeHtml(label)}</button>`
      );
    })
    .join("");

  const first = flowGraphs[0];
  const meta =
    `${first.graph?.nodes?.length || 0} task(s), ${first.graph?.edges?.length || 0} transition(s)` +
    ` · unreachable tasks shown dimmed`;

  return `
    <section class="flow-graphs-section">
      <h3>Playbook flows ${analysisHelpButton(
        "Visual map of each playbook file: tasks as nodes, nextTasks as edges.",
        "<p>Use this to understand <strong>what the playbook looks like</strong> and navigate by task #. " +
          "Switch tabs for sub-playbooks. Saved view placement uses canvas coordinates from the tenant. " +
          "Unreachable tasks are dimmed or hidden.</p>",
      )}</h3>
      <p class="meta">Task-level flow for each playbook in the tree. Arrows follow <code>nextTasks</code> with branch labels. Click a node for metadata; drag the background to pan; scroll to zoom.</p>
      <div class="flow-graph-nav" role="tablist" aria-label="Playbook flow views">${nav}</div>
      <p class="meta flow-graph-meta" id="flow-graph-meta-${escapeHtml(panelKey)}">${escapeHtml(meta)}</p>
      <div id="flow-graph-host-${escapeHtml(panelKey)}" class="flow-graph-host" role="tabpanel" data-panel-key="${escapeHtml(panelKey)}"></div>
      <div id="flow-graph-detail-${escapeHtml(panelKey)}" class="flow-graph-detail" aria-live="polite">
        <p class="meta">Click a task node, or jump by task #, to inspect metadata.</p>
      </div>
    </section>
  `;
}

function flowNodeIndex(graph) {
  return Object.fromEntries((graph?.nodes || []).map((node) => [flowNodeMermaidId(node.id), node]));
}

function flowNodeEdges(graph, taskId) {
  const outgoing = (graph?.edges || [])
    .filter((edge) => edge.from === taskId)
    .map((edge) => ({
      direction: "out",
      peer: edge.to,
      condition: edge.condition || "(default)",
    }));
  const incoming = (graph?.edges || [])
    .filter((edge) => edge.to === taskId)
    .map((edge) => ({
      direction: "in",
      peer: edge.from,
      condition: edge.condition || "(default)",
    }));
  return [...incoming, ...outgoing];
}

function flowDetailField(label, value) {
  if (value == null || value === "") {
    return "";
  }
  return `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd>`;
}

function flowRawTaskText(node, format = "json") {
  if (format === "yaml") {
    return node.raw_task_yaml || "(YAML not available for this task)";
  }
  return JSON.stringify(node.raw_task || {}, null, 2);
}

function buildFlowRawTaskHtml(node, format = "json") {
  const showJson = format !== "yaml";
  return (
    `<details class="flow-raw-task">` +
    `<summary>Raw task data</summary>` +
    `<div class="flow-raw-format-bar">` +
    `<button type="button" class="flow-raw-format${showJson ? " active" : ""}" data-format="json">JSON</button>` +
    `<button type="button" class="flow-raw-format${showJson ? "" : " active"}" data-format="yaml">YAML</button>` +
    `</div>` +
    `<pre class="flow-raw-task-body">${escapeHtml(flowRawTaskText(node, format))}</pre>` +
    `</details>`
  );
}

function bindFlowRawTaskFormatToggle(detailHost, node) {
  detailHost.querySelectorAll(".flow-raw-format").forEach((button) => {
    button.addEventListener("click", () => {
      const format = button.dataset.format || "json";
      detailHost.dataset.rawFormat = format;
      detailHost.querySelectorAll(".flow-raw-format").forEach((item) => {
        item.classList.toggle("active", item.dataset.format === format);
      });
      const body = detailHost.querySelector(".flow-raw-task-body");
      if (body && node) {
        body.textContent = flowRawTaskText(node, format);
      }
    });
  });
}

function buildFlowNodeDetailHtml(node, graph, entry, rawFormat = "json") {
  if (!node) {
    return `<p class="meta">Click a task node, or jump by task #, to inspect metadata.</p>`;
  }
  const edges = flowNodeEdges(graph, node.id);
  const edgeRows = edges.length
    ? edges
        .map((edge) => {
          const arrow = edge.direction === "out" ? "→" : "←";
          return (
            `<tr><td>${arrow}</td>` +
            `<td><button type="button" class="flow-peer-link" data-task-id="${escapeHtml(edge.peer)}">#${escapeHtml(edge.peer)}</button></td>` +
            `<td>${escapeHtml(edge.condition)}</td></tr>`
          );
        })
        .join("")
    : `<tr><td colspan="3">No transitions</td></tr>`;

  const binding =
    node.is_command && node.command
      ? node.command
      : node.script_name || node.detail || "—";

  const subPlaybookFlowIndex =
    node.playbook_name && entry?.playbook_name !== node.playbook_name
      ? (entry?._allFlowGraphs || []).findIndex((item) => item.playbook_name === node.playbook_name)
      : -1;
  const refactorActions =
    `<div class="flow-graph-refactor-actions">` +
    `<button type="button" class="flow-add-leaf-refactor" data-task-id="${escapeHtml(node.id)}">Add leaf extract</button>` +
    (subPlaybookFlowIndex >= 0
      ? `<button type="button" class="flow-open-sub-playbook" data-flow-index="${subPlaybookFlowIndex}">Open sub-playbook flow</button>`
      : "") +
    `</div>`;

  return (
    `<div class="flow-graph-detail-card">` +
    `<div class="flow-graph-detail-head">` +
    `<h4>Task #${escapeHtml(node.id)}</h4>` +
    `<button type="button" class="flow-copy-task-id" data-task-id="${escapeHtml(node.id)}">Copy #</button>` +
    `</div>` +
    refactorActions +
    `<dl class="flow-graph-detail-fields">` +
    flowDetailField("Name", node.label) +
    flowDetailField("Type", node.task_type) +
    flowDetailField("Binding", binding) +
    flowDetailField("Script", node.script_name) +
    flowDetailField("Script ID", node.script_id) +
    flowDetailField("Sub-playbook", node.playbook_name) +
    flowDetailField("Sub-playbook ID", node.playbook_id) +
    flowDetailField("Command raw", node.command_raw || node.script_binding) +
    flowDetailField("Description", node.description) +
    flowDetailField("Reachable", node.reachable ? "Yes" : "No") +
    flowDetailField("Start task", graph.start_task_id === node.id ? "Yes" : "No") +
    flowDetailField("Playbook", entry?.playbook_name) +
    `</dl>` +
    `<table class="analysis-table flow-graph-edge-table">` +
    `<thead><tr><th></th><th>Task</th><th>Condition</th></tr></thead>` +
    `<tbody>${edgeRows}</tbody></table>` +
    buildFlowRawTaskHtml(node, rawFormat) +
    `</div>`
  );
}

function findFlowNodeGroup(host, mermaidId, taskId = null) {
  if (!host) {
    return null;
  }
  if (taskId) {
    const savedNode = host.querySelector(`g.node[data-task-id="${CSS.escape(String(taskId))}"]`);
    if (savedNode) {
      return savedNode;
    }
  }
  if (!mermaidId) {
    return null;
  }
  return (
    host.querySelector(`g.node[id$="-${mermaidId}-0"]`) ||
    [...host.querySelectorAll("g.node")].find((group) => group.id.includes(`-${mermaidId}-`))
  );
}

function highlightFlowNeighborhood(host, graph, taskId) {
  if (!host) {
    return;
  }
  host.querySelectorAll("g.node.flow-neighbor").forEach((item) => item.classList.remove("flow-neighbor"));
  if (!taskId) {
    return;
  }
  const peers = new Set(flowNodeEdges(graph, taskId).map((edge) => edge.peer));
  for (const peerId of peers) {
    const group = findFlowNodeGroup(host, flowNodeMermaidId(peerId), peerId);
    group?.classList.add("flow-neighbor");
  }
}

function selectFlowNode(host, graph, detailHost, entry, taskId) {
  if (!host || !graph || !taskId) {
    return false;
  }
  const node = (graph.nodes || []).find((item) => item.id === String(taskId));
  if (!node) {
    return false;
  }
  host.querySelectorAll("g.node.selected-flow-node").forEach((item) => item.classList.remove("selected-flow-node"));
  const group = findFlowNodeGroup(host, flowNodeMermaidId(node.id), node.id);
  group?.classList.add("selected-flow-node");
  highlightFlowNeighborhood(host, graph, node.id);
  if (detailHost) {
    const rawFormat = detailHost.dataset.rawFormat || "json";
    detailHost.innerHTML = buildFlowNodeDetailHtml(node, graph, entry, rawFormat);
    bindFlowRawTaskFormatToggle(detailHost, node);
  }
  host.dataset.selectedTaskId = node.id;
  const jumpInput = host.querySelector(".flow-graph-jump-input");
  if (jumpInput) {
    jumpInput.value = node.id;
  }
  group?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
  return true;
}

function bindFlowGraphDetailActions(host, graph, detailHost, entry, details) {
  if (!detailHost) {
    return;
  }
  detailHost.onclick = (event) => {
    const peer = event.target.closest(".flow-peer-link");
    if (peer?.dataset.taskId) {
      selectFlowNode(host, graph, detailHost, entry, peer.dataset.taskId);
      return;
    }
    const copyBtn = event.target.closest(".flow-copy-task-id");
    if (copyBtn?.dataset.taskId && navigator.clipboard?.writeText) {
      void navigator.clipboard.writeText(copyBtn.dataset.taskId);
      return;
    }
    const leafBtn = event.target.closest(".flow-add-leaf-refactor");
    if (leafBtn?.dataset.taskId && details) {
      const panel = details.querySelector(".refactor-panel");
      if (panel) {
        addRefactorOperation(panel, "leaf", leafBtn.dataset.taskId, details._analysisData);
        panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
      return;
    }
    const subBtn = event.target.closest(".flow-open-sub-playbook");
    if (subBtn?.dataset.flowIndex != null && details?._flowGraphShow) {
      details._flowGraphShow(Number(subBtn.dataset.flowIndex));
    }
  };
}

function bindFlowGraphNodeClicks(host, graph, detailHost, entry, details) {
  if (!host || !graph) {
    return;
  }
  entry._allFlowGraphs = entry._allFlowGraphs || [];
  const nodeIndex = flowNodeIndex(graph);
  host._flowNodeIndex = nodeIndex;

  host.querySelector(".flow-graph-stage")?.addEventListener("click", (event) => {
    const group = event.target.closest("g.node");
    if (!group) {
      return;
    }
    if (group.dataset.taskId) {
      selectFlowNode(host, graph, detailHost, entry, group.dataset.taskId);
      return;
    }
    if (!group.id) {
      return;
    }
    const match = group.id.match(/-(t[\w]+)-\d+$/);
    const mermaidId = match ? match[1] : null;
    const node = mermaidId ? nodeIndex[mermaidId] : null;
    if (!node) {
      return;
    }
    selectFlowNode(host, graph, detailHost, entry, node.id);
  });
  bindFlowGraphDetailActions(host, graph, detailHost, entry, details);
}

const FLOW_GRAPH_VIEW_PAD = 32;
const FLOW_GRAPH_MIN_VIEW_SIZE = 140;
const FLOW_START_TASK_VIEWPORT_FRACTION = 0.1;
const FLOW_GRAPH_STAGE_HEIGHT_PCTS = [50, 60, 70, 80, 90];
const FLOW_GRAPH_DEFAULT_STAGE_HEIGHT_PCT = 60;

function normalizeFlowGraphStageHeightPct(pct) {
  const value = Number(pct);
  if (FLOW_GRAPH_STAGE_HEIGHT_PCTS.includes(value)) {
    return value;
  }
  return FLOW_GRAPH_DEFAULT_STAGE_HEIGHT_PCT;
}

function flowGraphStageHeightPx(pct) {
  return Math.round((window.innerHeight * normalizeFlowGraphStageHeightPct(pct)) / 100);
}

function stepFlowGraphStageHeightPct(current, delta) {
  const normalized = normalizeFlowGraphStageHeightPct(current);
  const index = FLOW_GRAPH_STAGE_HEIGHT_PCTS.indexOf(normalized);
  const nextIndex = Math.min(
    FLOW_GRAPH_STAGE_HEIGHT_PCTS.length - 1,
    Math.max(0, index + delta),
  );
  return FLOW_GRAPH_STAGE_HEIGHT_PCTS[nextIndex];
}

function applyFlowGraphStageHeight(host, viewState, preserveZoom = true) {
  const stage = host?.querySelector(".flow-graph-stage");
  if (!stage || !viewState) {
    return;
  }
  const pct = normalizeFlowGraphStageHeightPct(viewState.stageHeightPct);
  viewState.stageHeightPct = pct;
  const oldHeight = stage.clientHeight || flowGraphStageHeightPx(pct);
  const newHeight = flowGraphStageHeightPx(pct);
  stage.style.height = `${newHeight}px`;

  const state = host._flowViewState;
  if (preserveZoom && state?.vw && state?.vh && oldHeight > 0 && oldHeight !== newHeight) {
    const centerY = state.vy + state.vh / 2;
    state.vh = state.vh * (newHeight / oldHeight);
    state.vy = centerY - state.vh / 2;
    applyFlowGraphViewBox(host);
    syncFlowViewState(host, viewState);
  }

  const label = host.querySelector(".flow-graph-height-value");
  if (label) {
    label.textContent = `${pct}%`;
  }
  const downButton = host.querySelector(".flow-graph-height-down");
  const upButton = host.querySelector(".flow-graph-height-up");
  if (downButton) {
    downButton.disabled = pct <= FLOW_GRAPH_STAGE_HEIGHT_PCTS[0];
  }
  if (upButton) {
    upButton.disabled = pct >= FLOW_GRAPH_STAGE_HEIGHT_PCTS[FLOW_GRAPH_STAGE_HEIGHT_PCTS.length - 1];
  }
}

function ensureFlowGraphHeightResizeBinding() {
  if (window._flowGraphHeightResizeBound) {
    return;
  }
  window._flowGraphHeightResizeBound = true;
  window.addEventListener("resize", () => {
    document.querySelectorAll("[id^='flow-graph-host-']").forEach((host) => {
      const details = host.closest("details");
      const viewState = details?._flowGraphViewState;
      if (viewState) {
        applyFlowGraphStageHeight(host, viewState);
      }
    });
  });
}

function syncFlowViewState(host, viewState) {
  if (!host?._flowViewState || !viewState) {
    return;
  }
  const state = host._flowViewState;
  viewState.viewBox = {
    x: state.vx,
    y: state.vy,
    width: state.vw,
    height: state.vh,
  };
}

function flowGraphStageSize(host) {
  const stage = host.querySelector(".flow-graph-stage");
  if (!stage) {
    return null;
  }
  return { width: stage.clientWidth, height: stage.clientHeight };
}

function flowGraphContentBBox(host) {
  const svg = host.querySelector(".flow-graph-stage svg");
  if (!svg) {
    return null;
  }
  const contentRoot = svg.querySelector("g.root") || svg;
  const bbox = contentRoot.getBBox();
  if (!bbox.width || !bbox.height) {
    return null;
  }
  return bbox;
}

function flowGraphContentBounds(state) {
  const bbox = state.contentBbox;
  const pad = FLOW_GRAPH_VIEW_PAD;
  return {
    x: bbox.x - pad,
    y: bbox.y - pad,
    width: bbox.width + pad * 2,
    height: bbox.height + pad * 2,
  };
}

function applyFlowGraphViewBox(host) {
  const svg = host.querySelector(".flow-graph-stage svg");
  const state = host._flowViewState;
  if (!svg || !state || !state.vw || !state.vh) {
    return;
  }
  svg.setAttribute("viewBox", `${state.vx} ${state.vy} ${state.vw} ${state.vh}`);
}

function clampFlowGraphViewBox(width, height, state) {
  const bounds = flowGraphContentBounds(state);
  const aspect = width / height;
  let nextWidth = Math.min(bounds.width * 1.25, Math.max(FLOW_GRAPH_MIN_VIEW_SIZE, width));
  let nextHeight = nextWidth / aspect;
  const maxHeight = bounds.height * 1.25;
  if (nextHeight > maxHeight) {
    nextHeight = maxHeight;
    nextWidth = nextHeight * aspect;
  }
  nextHeight = Math.max(FLOW_GRAPH_MIN_VIEW_SIZE / aspect, nextHeight);
  return { width: nextWidth, height: nextHeight };
}

function requestFlowGraphStartFocus(viewState) {
  if (!viewState) {
    return;
  }
  viewState.viewBox = null;
  viewState.focusStartTask = true;
}

function resolveFlowGraphStartTaskId(graph) {
  if (graph?.start_task_id) {
    return String(graph.start_task_id);
  }
  const startNode = (graph?.nodes || []).find(
    (node) => node.is_start || node.task_type === "start",
  );
  if (startNode) {
    return String(startNode.id);
  }
  const numericIds = (graph?.nodes || [])
    .map((node) => node.id)
    .filter((taskId) => /^\d+$/.test(String(taskId)))
    .map((taskId) => Number(taskId));
  if (numericIds.length) {
    return String(Math.min(...numericIds));
  }
  return graph?.nodes?.[0]?.id ? String(graph.nodes[0].id) : null;
}

function flowGraphNodeBounds(host, taskId, graph, viewState = null) {
  const group = findFlowNodeGroup(host, flowNodeMermaidId(taskId), taskId);
  const svg = host.querySelector(".flow-graph-stage svg");
  if (group && svg && typeof group.getBBox === "function") {
    const box = group.getBBox();
    if (typeof group.getCTM === "function" && typeof svg.createSVGPoint === "function") {
      const matrix = group.getCTM();
      if (matrix) {
        const points = [
          { x: box.x, y: box.y },
          { x: box.x + box.width, y: box.y },
          { x: box.x + box.width, y: box.y + box.height },
          { x: box.x, y: box.y + box.height },
        ];
        const xs = [];
        const ys = [];
        for (const point of points) {
          const svgPoint = svg.createSVGPoint();
          svgPoint.x = point.x;
          svgPoint.y = point.y;
          const transformed = svgPoint.matrixTransform(matrix);
          xs.push(transformed.x);
          ys.push(transformed.y);
        }
        const x = Math.min(...xs);
        const y = Math.min(...ys);
        return {
          x,
          y,
          width: Math.max(...xs) - x,
          height: Math.max(...ys) - y,
        };
      }
    }
    if (box.width && box.height) {
      return box;
    }
  }
  const node = (graph?.nodes || []).find((item) => item.id === String(taskId));
  const pos = parseTaskViewPosition(node?.raw_task);
  if (pos) {
    const metrics = flowSavedMetrics(viewState || host._flowViewState || {});
    return {
      x: pos.x,
      y: pos.y,
      width: metrics.width,
      height: metrics.height,
    };
  }
  return null;
}

function alignFlowGraphViewTop(host, viewState = null) {
  const state = host._flowViewState;
  if (!state?.contentBbox) {
    return;
  }
  const bounds = flowGraphContentBounds(state);
  state.vy = bounds.y;
  applyFlowGraphViewBox(host);
  syncFlowViewState(host, viewState);
}

function focusFlowGraphOnStartTask(host, graph, viewState = null) {
  const stageSize = flowGraphStageSize(host);
  const state = host._flowViewState;
  if (!stageSize || !state?.contentBbox || !graph) {
    return;
  }
  const startTaskId = resolveFlowGraphStartTaskId(graph);
  const nodeBounds = startTaskId ? flowGraphNodeBounds(host, startTaskId, graph, viewState) : null;
  if (!startTaskId || !nodeBounds?.width || !nodeBounds?.height) {
    fitFlowGraphToView(host, viewState);
    alignFlowGraphViewTop(host, viewState);
    return;
  }

  const stageAspect = stageSize.width / stageSize.height;
  const viewWidth = Math.max(
    nodeBounds.width / FLOW_START_TASK_VIEWPORT_FRACTION,
    FLOW_GRAPH_MIN_VIEW_SIZE,
  );
  const viewHeight = viewWidth / stageAspect;
  const centerX = nodeBounds.x + nodeBounds.width / 2;
  const centerY = nodeBounds.y + nodeBounds.height / 2;
  state.vx = centerX - viewWidth / 2;
  state.vy = centerY - viewHeight / 2;
  state.vw = viewWidth;
  state.vh = viewHeight;
  applyFlowGraphViewBox(host);
  syncFlowViewState(host, viewState);
}

function initFlowGraphReadableView(host, viewState = null) {
  const stageSize = flowGraphStageSize(host);
  const state = host._flowViewState;
  if (!stageSize || !state?.contentBbox) {
    return;
  }
  const bounds = flowGraphContentBounds(state);
  state.vw = stageSize.width;
  state.vh = stageSize.height;
  state.vx = bounds.x;
  state.vy = bounds.y;
  applyFlowGraphViewBox(host);
  syncFlowViewState(host, viewState);
}

function fitFlowGraphToView(host, viewState = null) {
  const stageSize = flowGraphStageSize(host);
  const state = host._flowViewState;
  if (!stageSize?.width || !stageSize?.height || !state?.contentBbox) {
    return;
  }
  const bounds = flowGraphContentBounds(state);
  const contentAspect = bounds.width / bounds.height;
  const stageAspect = stageSize.width / stageSize.height;
  let viewWidth = bounds.width;
  let viewHeight = bounds.height;
  if (contentAspect > stageAspect) {
    viewHeight = bounds.width / stageAspect;
  } else {
    viewWidth = bounds.height * stageAspect;
  }
  state.vx = bounds.x - (viewWidth - bounds.width) / 2;
  state.vy = bounds.y - (viewHeight - bounds.height) / 2;
  state.vw = viewWidth;
  state.vh = viewHeight;
  applyFlowGraphViewBox(host);
  syncFlowViewState(host, viewState);
}

function resetFlowGraphView(host, viewState = null) {
  initFlowGraphReadableView(host, viewState);
}

function zoomFlowGraphAt(host, factor, clientX = null, clientY = null, viewState = null) {
  const stage = host.querySelector(".flow-graph-stage");
  const state = host._flowViewState;
  if (!stage || !state) {
    return;
  }
  const rect = stage.getBoundingClientRect();
  const mx = clientX == null ? rect.width / 2 : clientX - rect.left;
  const my = clientY == null ? rect.height / 2 : clientY - rect.top;
  const oldWidth = state.vw;
  const oldHeight = state.vh;
  const clamped = clampFlowGraphViewBox(oldWidth * factor, oldHeight * factor, state);
  const newWidth = clamped.width;
  const newHeight = clamped.height;
  const svgX = state.vx + (mx / rect.width) * oldWidth;
  const svgY = state.vy + (my / rect.height) * oldHeight;
  state.vx = svgX - (mx / rect.width) * newWidth;
  state.vy = svgY - (my / rect.height) * newHeight;
  state.vw = newWidth;
  state.vh = newHeight;
  applyFlowGraphViewBox(host);
  syncFlowViewState(host, viewState);
}

function setupFlowGraphViewport(host, viewState = null, graph = null) {
  const bbox = flowGraphContentBBox(host);
  if (!bbox) {
    return;
  }
  host._flowViewState = host._flowViewState || {};
  host._flowViewState.contentBbox = bbox;

  if (viewState?.focusStartTask && graph) {
    viewState.focusStartTask = false;
    focusFlowGraphOnStartTask(host, graph, viewState);
    return;
  }

  const saved = viewState?.viewBox;
  if (saved?.width && saved?.height) {
    host._flowViewState.vx = saved.x;
    host._flowViewState.vy = saved.y;
    host._flowViewState.vw = saved.width;
    host._flowViewState.vh = saved.height;
    applyFlowGraphViewBox(host);
    syncFlowViewState(host, viewState);
    return;
  }

  initFlowGraphReadableView(host, viewState);
}

function finalizeFlowGraphSvg(host) {
  const stage = host.querySelector(".flow-graph-stage");
  const svg = stage?.querySelector("svg");
  if (!stage || !svg) {
    return;
  }
  if (svg.parentElement !== stage) {
    stage.innerHTML = "";
    stage.appendChild(svg);
  }
  svg.style.maxWidth = "none";
  svg.style.width = "100%";
  svg.style.height = "100%";
  svg.style.display = "block";
  svg.setAttribute("width", "100%");
  svg.setAttribute("height", "100%");
  svg.setAttribute("preserveAspectRatio", "none");
}

function ensureFlowGraphViewportBindings(host) {
  if (host.dataset.viewportBound) {
    return;
  }
  host.dataset.viewportBound = "1";
  host._flowViewState = host._flowViewState || {};
  host._flowPanning = false;

  host.addEventListener(
    "wheel",
    (event) => {
      const stage = event.target.closest(".flow-graph-stage");
      if (!stage || !host.contains(stage)) {
        return;
      }
      event.preventDefault();
      const factor = event.deltaY > 0 ? 1.12 : 1 / 1.12;
      zoomFlowGraphAt(host, factor, event.clientX, event.clientY);
    },
    { passive: false },
  );

  host.addEventListener("mousedown", (event) => {
    const stage = event.target.closest(".flow-graph-stage");
    if (!stage || !host.contains(stage) || event.button !== 0 || event.target.closest("g.node")) {
      return;
    }
    host._flowPanning = true;
    host._flowPanX = event.clientX;
    host._flowPanY = event.clientY;
    stage.classList.add("flow-graph-panning");
  });

  window.addEventListener("mousemove", (event) => {
    if (!host._flowPanning) {
      return;
    }
    const stage = host.querySelector(".flow-graph-stage");
    const viewState = host._flowViewState;
    if (!stage || !viewState?.vw) {
      return;
    }
    const dx = event.clientX - host._flowPanX;
    const dy = event.clientY - host._flowPanY;
    viewState.vx -= dx * (viewState.vw / stage.clientWidth);
    viewState.vy -= dy * (viewState.vh / stage.clientHeight);
    host._flowPanX = event.clientX;
    host._flowPanY = event.clientY;
    applyFlowGraphViewBox(host);
  });

  window.addEventListener("mouseup", () => {
    if (!host._flowPanning) {
      return;
    }
    host._flowPanning = false;
    host.querySelector(".flow-graph-stage")?.classList.remove("flow-graph-panning");
  });
}

function buildFlowGraphShellHtml(renderId, viewState) {
  const hideChecked = viewState.hideUnreachable ? " checked" : "";
  const savedViewChecked = flowGraphUsesSavedView(viewState) ? " checked" : "";
  const lrActive = viewState.direction === "LR" ? " active" : "";
  const tdActive = viewState.direction === "TD" ? " active" : "";
  const heightPct = normalizeFlowGraphStageHeightPct(viewState.stageHeightPct);
  const stageHeight = flowGraphStageHeightPx(heightPct);
  const atMinHeight = heightPct <= FLOW_GRAPH_STAGE_HEIGHT_PCTS[0];
  const atMaxHeight = heightPct >= FLOW_GRAPH_STAGE_HEIGHT_PCTS[FLOW_GRAPH_STAGE_HEIGHT_PCTS.length - 1];
  const savedScale = flowSavedNodeScale(viewState);
  const scaleHidden = flowGraphUsesSavedView(viewState) ? "" : " hidden";
  return (
    `<div class="flow-graph-shell">` +
    `<div class="flow-graph-toolbar">` +
    `<label class="flow-graph-jump">Task # <input type="text" class="flow-graph-jump-input" inputmode="numeric" placeholder="id" /></label>` +
    `<label class="flow-graph-toggle"><input type="checkbox" class="flow-graph-hide-unreachable"${hideChecked} /> Hide unreachable</label>` +
    `<label class="flow-graph-toggle" title="Place nodes using each task's saved canvas view position">` +
    `<input type="checkbox" class="flow-graph-saved-view"${savedViewChecked} /> Use Saved View Placement</label>` +
    `<label class="flow-graph-scale${scaleHidden}" title="Node size when saved view placement is on">` +
    `Node size` +
    `<input type="range" class="flow-graph-saved-scale" min="${FLOW_SAVED_SCALE_MIN}" max="${FLOW_SAVED_SCALE_MAX}" step="0.1" value="${savedScale}" />` +
    `<span class="flow-graph-scale-value">${savedScale.toFixed(1)}×</span>` +
    `</label>` +
    `<label class="flow-graph-height" title="Viewport height (% of window)">` +
    `Height` +
    `<button type="button" class="flow-graph-height-down" title="Decrease viewport height"${atMinHeight ? " disabled" : ""}>−</button>` +
    `<span class="flow-graph-height-value">${heightPct}%</span>` +
    `<button type="button" class="flow-graph-height-up" title="Increase viewport height"${atMaxHeight ? " disabled" : ""}>+</button>` +
    `</label>` +
    `<button type="button" class="flow-graph-layout${lrActive}" data-direction="LR" title="Layout: flow runs left to right (horizontal)">Left → right</button>` +
    `<button type="button" class="flow-graph-layout${tdActive}" data-direction="TD" title="Layout: flow runs top to bottom (vertical)">Top → down</button>` +
    `<button type="button" class="flow-graph-zoom-out" title="Zoom out">−</button>` +
    `<button type="button" class="flow-graph-zoom-in" title="Zoom in">+</button>` +
    `<button type="button" class="flow-graph-fit">Fit</button>` +
    `<button type="button" class="flow-graph-reset" title="Reset to readable zoom at flow start">Reset</button>` +
    `</div>` +
    `<div class="flow-graph-stage" style="height:${stageHeight}px"><pre class="mermaid" id="${escapeHtml(renderId)}"></pre></div>` +
    `</div>`
  );
}

function updateFlowGraphMeta(metaHost, entry, graph, viewState) {
  if (!metaHost) {
    return;
  }
  const hiddenCount = viewState.hideUnreachable
    ? (entry.graph?.nodes || []).filter((node) => !node.reachable).length
    : 0;
  const placement = flowGraphUsesSavedView(viewState) ? "saved canvas placement" : "auto layout";
  metaHost.textContent =
    `${entry.playbook_name}: ${graph.nodes.length} task(s), ${graph.edges.length} transition(s)` +
    (hiddenCount ? ` · ${hiddenCount} unreachable hidden` : " · unreachable dimmed") +
    ` · ${placement}` +
    " · drag to pan, scroll to zoom · Reset = readable · Fit = full flow";
}

function bindFlowGraphToolbar(host, entry, viewState, rerender) {
  const jumpInput = host.querySelector(".flow-graph-jump-input");
  if (jumpInput && host.dataset.selectedTaskId) {
    jumpInput.value = host.dataset.selectedTaskId;
  }
  const hideToggle = host.querySelector(".flow-graph-hide-unreachable");
  if (hideToggle) {
    hideToggle.checked = viewState.hideUnreachable;
  }
  host.querySelectorAll(".flow-graph-layout").forEach((button) => {
    button.classList.toggle("active", button.dataset.direction === viewState.direction);
  });
  syncFlowGraphLayoutControls(host, viewState);
  applyFlowGraphStageHeight(host, viewState);

  if (host.dataset.toolbarBound) {
    return;
  }
  host.dataset.toolbarBound = "1";

  host.addEventListener("click", (event) => {
    if (event.target.closest(".flow-graph-fit")) {
      fitFlowGraphToView(host, viewState);
      return;
    }
    if (event.target.closest(".flow-graph-reset")) {
      resetFlowGraphView(host, viewState);
      return;
    }
    if (event.target.closest(".flow-graph-zoom-in")) {
      zoomFlowGraphAt(host, 1 / 1.2, null, null, viewState);
      return;
    }
    if (event.target.closest(".flow-graph-zoom-out")) {
      zoomFlowGraphAt(host, 1.2, null, null, viewState);
      return;
    }
    if (event.target.closest(".flow-graph-height-down")) {
      viewState.stageHeightPct = stepFlowGraphStageHeightPct(viewState.stageHeightPct, -1);
      applyFlowGraphStageHeight(host, viewState);
      return;
    }
    if (event.target.closest(".flow-graph-height-up")) {
      viewState.stageHeightPct = stepFlowGraphStageHeightPct(viewState.stageHeightPct, 1);
      applyFlowGraphStageHeight(host, viewState);
      return;
    }
    const layoutButton = event.target.closest(".flow-graph-layout");
    if (layoutButton) {
      viewState.direction = layoutButton.dataset.direction;
      requestFlowGraphStartFocus(viewState);
      rerender();
    }
  });

  host.addEventListener("keydown", (event) => {
    const jumpInput = event.target.closest(".flow-graph-jump-input");
    if (!jumpInput || event.key !== "Enter") {
      return;
    }
    const taskId = jumpInput.value.trim();
    const detailHost = document.getElementById(`flow-graph-detail-${host.dataset.panelKey}`);
    if (!selectFlowNode(host, filterFlowGraph(entry.graph, viewState), detailHost, entry, taskId)) {
      jumpInput.classList.add("flow-graph-jump-error");
      window.setTimeout(() => jumpInput.classList.remove("flow-graph-jump-error"), 600);
    }
  });

  host.addEventListener("change", (event) => {
    if (event.target.matches(".flow-graph-hide-unreachable")) {
      viewState.hideUnreachable = event.target.checked;
      requestFlowGraphStartFocus(viewState);
      rerender();
      return;
    }
    if (event.target.matches(".flow-graph-saved-view")) {
      viewState.useSavedViewPlacement = event.target.checked;
      requestFlowGraphStartFocus(viewState);
      rerender();
      return;
    }
    if (event.target.matches(".flow-graph-saved-scale")) {
      viewState.savedNodeScale = Number(event.target.value);
      const valueEl = host.querySelector(".flow-graph-scale-value");
      if (valueEl) {
        valueEl.textContent = `${flowSavedNodeScale(viewState).toFixed(1)}×`;
      }
      requestFlowGraphStartFocus(viewState);
      rerender();
    }
  });

  host.addEventListener("input", (event) => {
    if (!event.target.matches(".flow-graph-saved-scale")) {
      return;
    }
    const valueEl = host.querySelector(".flow-graph-scale-value");
    if (valueEl) {
      valueEl.textContent = `${Number(event.target.value).toFixed(1)}×`;
    }
  });
}

async function renderFlowGraph(hostId, entry, metaHostId, detailHostId, viewState) {
  const host = document.getElementById(hostId);
  const metaHost = metaHostId ? document.getElementById(metaHostId) : null;
  const detailHost = detailHostId ? document.getElementById(detailHostId) : null;
  const graph = filterFlowGraph(entry.graph, viewState);
  if (!host) {
    return;
  }
  ensureFlowGraphViewportBindings(host);
  syncFlowViewState(host, viewState);
  if (!graph?.nodes?.length) {
    host.innerHTML = '<p class="meta">No tasks to display (try showing unreachable tasks).</p>';
    return;
  }
  updateFlowGraphMeta(metaHost, entry, graph, viewState);
  const renderId = `${hostId}-mermaid`;
  host.innerHTML = buildFlowGraphShellHtml(renderId, viewState);
  bindFlowGraphToolbar(host, entry, viewState, () => {
    void renderFlowGraph(hostId, entry, metaHostId, detailHostId, viewState);
  });

  const useSavedView = flowGraphUsesSavedView(viewState) && graphHasSavedViewPositions(graph);
  try {
    if (useSavedView && mountFlowSavedViewSvg(host, graph, viewState)) {
      finalizeFlowGraphSvg(host);
      setupFlowGraphViewport(host, viewState, graph);
      bindFlowGraphNodeClicks(host, graph, detailHost, entry, host.closest("details.analysis-panel"));
      if (host.dataset.selectedTaskId) {
        selectFlowNode(host, graph, detailHost, entry, host.dataset.selectedTaskId);
      }
      return;
    }

    if (!ensureFlowGraphMermaidReady()) {
      host.innerHTML = '<p class="meta">Diagram library not loaded.</p>';
      return;
    }

    const source = buildFlowMermaidSource(graph, { direction: viewState.direction });
    const node = document.getElementById(renderId);
    if (!node) {
      return;
    }
    node.textContent = source;
    await mermaid.run({ nodes: [node] });
    finalizeFlowGraphSvg(host);
    setupFlowGraphViewport(host, viewState, graph);
    bindFlowGraphNodeClicks(host, graph, detailHost, entry, host.closest("details.analysis-panel"));
    if (host.dataset.selectedTaskId) {
      selectFlowNode(host, graph, detailHost, entry, host.dataset.selectedTaskId);
    }
  } catch (err) {
    host.innerHTML = `<p class="meta">Could not render flow diagram: ${escapeHtml(err.message || String(err))}</p>`;
  }
}

function bindFlowGraphNav(details, data, panelKey) {
  const flowGraphs = data.flow_graphs || [];
  if (!flowGraphs.length) {
    return;
  }
  const hostId = `flow-graph-host-${panelKey}`;
  const metaHostId = `flow-graph-meta-${panelKey}`;
  const detailHostId = `flow-graph-detail-${panelKey}`;
  const nav = details.querySelector(".flow-graph-nav");
  if (!nav) {
    return;
  }

  ensureFlowGraphHeightResizeBinding();

  const viewState = {
    hideUnreachable: false,
    useSavedViewPlacement: true,
    savedNodeScale: FLOW_SAVED_SCALE_DEFAULT,
    direction: null,
    viewBox: null,
    focusStartTask: true,
    stageHeightPct: FLOW_GRAPH_DEFAULT_STAGE_HEIGHT_PCT,
    index: 0,
  };
  details._flowGraphViewState = viewState;

  flowGraphs.forEach((entry) => {
    entry._allFlowGraphs = flowGraphs;
  });

  const showGraph = (index) => {
    const entry = flowGraphs[index];
    if (!entry) {
      return;
    }
    viewState.index = index;
    requestFlowGraphStartFocus(viewState);
    nav.querySelectorAll(".flow-graph-tab").forEach((button, buttonIndex) => {
      const active = buttonIndex === index;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    const detailHost = document.getElementById(detailHostId);
    if (detailHost) {
      detailHost.innerHTML = `<p class="meta">Click a task node, or jump by task #, to inspect metadata.</p>`;
    }
    void renderFlowGraph(hostId, entry, metaHostId, detailHostId, viewState);
  };

  nav.querySelectorAll(".flow-graph-tab").forEach((button) => {
    button.addEventListener("click", () => {
      const host = document.getElementById(hostId);
      if (host) {
        delete host.dataset.selectedTaskId;
      }
      showGraph(Number(button.dataset.flowIndex));
    });
  });

  details._flowGraphShow = showGraph;
  details._selectFlowTask = (taskId, flowIndex = null) => {
    if (flowIndex != null) {
      showGraph(flowIndex);
    }
    const host = document.getElementById(hostId);
    const entry = flowGraphs[viewState.index];
    const graph = filterFlowGraph(entry?.graph, viewState);
    const detailHost = document.getElementById(detailHostId);
    if (host && graph && taskId) {
      selectFlowNode(host, graph, detailHost, entry, String(taskId));
    }
  };

  showGraph(0);
}

function bindStructureTreeNavigation(details) {
  details.querySelectorAll(".structure-tree-link").forEach((button) => {
    button.addEventListener("click", () => {
      const flowIndex = Number(button.dataset.flowIndex);
      if (Number.isFinite(flowIndex) && details._flowGraphShow) {
        details._flowGraphShow(flowIndex);
        details.querySelector(".flow-graphs-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });
}

function buildNotesHtml(notes) {
  const items = notes || [];
  if (!items.length) {
    return `<p class="meta">No notes.</p>`;
  }
  const rows = items
    .map((note) => {
      const level = escapeHtml(note.level || "info");
      const message = escapeHtml(note.message || "");
      const detail = note.detail ? `<div class="analysis-note-detail">${escapeHtml(note.detail)}</div>` : "";
      return `<li class="analysis-note analysis-note-${level}"><strong>${level}</strong> ${message}${detail}</li>`;
    })
    .join("");
  return `<ul class="analysis-notes">${rows}</ul>`;
}

function buildAnalysisOverviewHtml(data, panelKey) {
  const scope = data.copy_scope || {};
  const totals = data.task_reachability_totals || {};
  const paths = data.completion_paths || {};
  const pathText =
    paths.min_tasks_to_completion != null && paths.max_tasks_to_completion != null
      ? `${paths.min_tasks_to_completion}–${paths.max_tasks_to_completion} sequential task(s)` +
        (paths.terminal_count ? ` · ${paths.terminal_count} terminal branch(es)` : "")
      : paths.note || "Unavailable";

  const cards = [
    {
      label: "Reachable tasks",
      value: `${totals.reachable || 0} / ${totals.total || 0}`,
      help: "Tasks reachable from the start node in the fully expanded playbook tree (main + sub-playbooks).",
    },
    {
      label: "Completion path",
      value: pathText,
      help: "Shortest and longest sequential paths from start to a terminal task in the expanded graph.",
    },
    {
      label: "Copy scope",
      value: `${scope.playbook_count || 0} PB · ${scope.script_count || 0} scripts`,
      help: "Playbooks and custom automation scripts that a deep copy would upload. Integration commands are not copied.",
    },
    {
      label: "Sub-playbooks",
      value: String((data.playbooks_in_tree || []).length),
      help: "Playbooks referenced in the tree (root + nested sub-playbook calls).",
    },
  ];

  const cardHtml = cards
    .map(
      (card) =>
        `<div class="analysis-stat-card">` +
        `<div class="analysis-stat-label">${escapeHtml(card.label)} ${analysisHelpButton(card.help)}</div>` +
        `<div class="analysis-stat-value">${escapeHtml(card.value)}</div>` +
        `</div>`,
    )
    .join("");

  const notes = (data.notes || []).length ? buildNotesHtml(data.notes) : "";

  return (
    `<section id="section-overview-${escapeHtml(panelKey)}" class="analysis-section">` +
    `<h3>Overview ${analysisHelpButton(
      "High-level metrics for navigation, copy planning, and refactor scope.",
      "<p>Start with <strong>Flow</strong> to see what the playbook looks like. Use <strong>Structure</strong> for nesting. " +
        "<strong>Task summary</strong> aggregates by type across the expanded tree. <strong>Inventory</strong> lists scripts and integrations.</p>",
    )}</h3>` +
    `<div class="analysis-overview-grid">${cardHtml}</div>` +
    notes +
    `</section>`
  );
}

function formatTaskSummaryList(values) {
  if (!Array.isArray(values) || !values.length) {
    return "—";
  }
  return values.join(", ");
}

function taskSummaryRowToCells(row) {
  return [
    row.task_type,
    row.label || "—",
    formatTaskSummaryList(row.scripts),
    formatTaskSummaryList(row.playbooks),
    formatTaskSummaryList(row.commands),
    row.count,
  ];
}

function buildTaskSummarySectionHtml(data, panelKey) {
  const summaryHeaders = ["Task type", "Label", "Scripts", "Playbooks", "Commands", "Count"];
  const reachableRows = (data.task_summary_reachable || []).map(taskSummaryRowToCells);
  const unreachableRows = (data.task_summary_unreachable || []).map(taskSummaryRowToCells);
  const allRows = (data.task_summary || []).map(taskSummaryRowToCells);
  return (
    `<section id="section-tasks-${escapeHtml(panelKey)}" class="analysis-section analysis-section-full">` +
    `<h3>Task summary ${analysisHelpButton(
      "Aggregated task counts by type and label, with script/playbook/command bindings.",
      "<p><strong>Reachable</strong> and <strong>Unreachable</strong> use the <strong>expanded execution graph</strong> (sub-playbooks inlined; reachability from start). " +
        "<strong>All tasks (reference)</strong> counts every task in each playbook file — no reachability filter, not expanded.</p>" +
        "<p>Per-task detail (including conditional branches and path metrics) is in <strong>Task list</strong>.</p>",
    )}</h3>` +
    `<div class="analysis-task-tabs" role="tablist">` +
    `<button type="button" class="analysis-task-tab active" data-task-tab="reachable" aria-pressed="true">Reachable (expanded graph)</button>` +
    `<button type="button" class="analysis-task-tab" data-task-tab="unreachable" aria-pressed="false">Unreachable (expanded graph)</button>` +
    `<button type="button" class="analysis-task-tab" data-task-tab="all" aria-pressed="false">All tasks (reference)</button>` +
    `</div>` +
    `<div class="analysis-task-panel" data-task-tab="reachable">` +
    `<p class="meta">Expanded graph — tasks on at least one execution path from start through inlined sub-playbooks.</p>` +
    renderAnalysisTableHtml(summaryHeaders, reachableRows) +
    `</div>` +
    `<div class="analysis-task-panel hidden" data-task-tab="unreachable">` +
    `<p class="meta">Expanded graph — tasks present in the tree but not on any execution path from start (e.g. dead branches).</p>` +
    renderAnalysisTableHtml(summaryHeaders, unreachableRows) +
    `</div>` +
    `<div class="analysis-task-panel hidden" data-task-tab="all">` +
    `<p class="meta">Per playbook file — all tasks by type and label. Not reachability-filtered; not the expanded graph.</p>` +
    renderAnalysisTableHtml(summaryHeaders, allRows) +
    `</div>` +
    `</section>`
  );
}

function buildAnalysisSectionNavHtml(panelKey) {
  const sections = [
    ["overview", "Overview"],
    ["flow", "Flow"],
    ["structure", "Structure"],
    ["tasks", "Tasks"],
    ["inventory", "Inventory"],
    ["detail", "Task list"],
    ["refactor", "Refactor"],
    ["copy", "Copy"],
  ];
  const links = sections
    .map(
      ([id, label], index) =>
        `<a href="#section-${id}-${escapeHtml(panelKey)}" class="${index === 1 ? "active" : ""}">${escapeHtml(label)}</a>`,
    )
    .join("");
  return `<nav class="analysis-section-nav" aria-label="Analysis sections">${links}</nav>`;
}

function buildAnalysisBodyHtml(data, panelKey) {
  const scope = data.copy_scope || {};
  const scopeDetail =
    `${scope.excluded_script_count || 0} system script(s) excluded · ` +
    `${scope.integration_command_count || 0} integration command(s) (reference only)` +
    (scope.missing_sub_playbook_count ? ` · ${scope.missing_sub_playbook_count} missing sub-playbook(s)` : "") +
    (scope.unresolved_script_count ? ` · ${scope.unresolved_script_count} unresolved script(s)` : "");

  return `
    ${buildAnalysisSectionNavHtml(panelKey)}
    ${buildAnalysisOverviewHtml(data, panelKey)}
    <section id="section-flow-${escapeHtml(panelKey)}" class="analysis-section">
      ${buildFlowGraphsSectionHtml(data, panelKey)}
    </section>
    <section id="section-structure-${escapeHtml(panelKey)}" class="analysis-section analysis-section-full">
      ${buildStructureSectionHtml(data, panelKey)}
    </section>
    ${buildTaskSummarySectionHtml(data, panelKey)}
    <section id="section-inventory-${escapeHtml(panelKey)}" class="analysis-section analysis-section-full">
      <h3>Inventory ${analysisHelpButton(
        "Scripts and playbooks referenced in the tree; integration commands the tenant must provide.",
        "<p><strong>Copyable</strong> custom scripts can be uploaded to another tenant. <strong>Integration commands</strong> (Brand|||command) are never copied — the target must have the integration configured.</p>",
      )}</h3>
      <p class="meta">${escapeHtml(scopeDetail)}</p>
      <div class="analysis-stack">
        <div class="analysis-block">
          <h4>Automation scripts</h4>
          ${renderAnalysisTableHtml(
            ["Script", "System", "Pack", "Copyable", "Count", "Resolved"],
            (data.scripts_used || []).map((row) => [
              row.name,
              row.system ? "Yes" : "No",
              row.pack_name || "—",
              row.copyable ? "Yes" : "No",
              row.count,
              row.resolved ? "Yes" : "No",
            ]),
          )}
        </div>
        <div class="analysis-block">
          <h4>Playbooks in tree</h4>
          ${renderAnalysisTableHtml(
            ["Playbook", "Role", "System", "Pack"],
            (data.playbooks_in_tree || []).map((row) => [
              row.name,
              row.role || "—",
              row.system ? "Yes" : "No",
              row.pack_name || "—",
            ]),
          )}
        </div>
        <div class="analysis-block">
          <h4>Integration commands (reference — not copied)</h4>
          ${buildCommandsTableHtml(data.integration_commands_used || data.commands_used)}
        </div>
      </div>
    </section>
    <section id="section-detail-${escapeHtml(panelKey)}" class="analysis-section analysis-section-full">
      <h3>Task list ${analysisHelpButton(
        "Every task in each playbook file, one row per task.",
        "<p><strong>Task #</strong> links focus the task in the <strong>Flow</strong> graph. " +
          "<strong>Reachable</strong> and step counts use the expanded execution graph from the workflow root. " +
          "<strong>Conditional branches</strong> — unique branch names from condition tasks on any path from that playbook's start to the task.</p>",
      )}</h3>
      <div class="playbook-task-listings">${buildPlaybookTaskListingsHtml(data)}</div>
    </section>
    <section id="section-refactor-${escapeHtml(panelKey)}" class="analysis-section analysis-section-full">
    <h3>Refactor ${analysisHelpButton(
      "Extract leaf or cluster tasks into sub-playbooks on the live tenant. Creates a new parent copy — never overwrites the source.",
      "<p><strong>Leaf extract</strong> — one task becomes a sub-playbook call. <strong>Cluster extract</strong> — a contiguous task range (START:END). " +
        "<strong>Error handling</strong> — after subs are uploaded and compared, apply retry/error settings to matching script tasks in generated sub-playbooks.</p>",
    )}</h3>
    <div class="refactor-panel" data-panel-key="${escapeHtml(panelKey)}">
        <p class="meta">
          Click a task in the flow graph to add a leaf extract. Preview before run.
        </p>
        <div class="refactor-toolbar refactor-config-row">
          <label>
            Load saved config
            <select class="refactor-preset-select">
              <option value="">— manual —</option>
            </select>
          </label>
          <button type="button" class="secondary refactor-load-preset-btn">Load config</button>
        </div>
        <div class="refactor-ops-list"></div>
        <div class="refactor-toolbar">
          <label>
            Add operation
            <select class="refactor-add-type">
              <option value="leaf">Leaf extract</option>
              <option value="cluster">Cluster extract</option>
              <option value="error">Error handling (post-refactor)</option>
            </select>
          </label>
          <button type="button" class="secondary refactor-add-btn">Add</button>
        </div>
        <label class="refactor-parent-copy">
          Parent copy name (optional)
          <input type="text" class="refactor-parent-copy-name" placeholder="Auto [REFACTOR-M] name" />
        </label>
        <label class="refactor-toggle" title="Experimental: upload/compare sub-playbooks in parallel within one extract-multi run">
          <input type="checkbox" class="refactor-parallel-checkbox" />
          Parallel extract-multi ${analysisHelpButton(
            "Runs sub-playbook upload and compare steps concurrently within this playbook refactor (experimental).",
          )}
        </label>
        <div class="refactor-actions">
          <button type="button" class="action refactor-preview-btn">Preview refactor</button>
          <button type="button" class="primary refactor-run-btn">Run refactor</button>
        </div>
      <div class="refactor-progress-panel hidden" aria-live="polite">
        <ul class="refactor-progress-timeline"></ul>
        <details class="refactor-progress-raw">
          <summary>Verbose log</summary>
          <pre class="refactor-progress-log"></pre>
        </details>
      </div>
      <div class="refactor-result-summary hidden"></div>
      <pre class="result refactor-result hidden"></pre>
    </div>
    </section>
    <section id="section-copy-${escapeHtml(panelKey)}" class="analysis-section">
    <h3>Deep copy ${analysisHelpButton(
      "Copy root playbook, reachable sub-playbooks, and custom scripts to another tenant profile.",
      "<p>Preview shows what will be copied vs skipped. Integration commands are never copied. " +
        "Use <strong>Overwrite</strong> to replace existing names on the target, or <strong>Stop on conflict</strong> to abort.</p>",
    )}</h3>
    <div class="copy-row analysis-copy-row">
      <label>
        Target profile
        <select class="analysis-components-target" data-source-profile="${escapeHtml(data.profile)}" data-panel-key="${escapeHtml(panelKey)}"></select>
      </label>
      <label class="checkbox" title="Replace playbook/script on target when the same name already exists">
        <input type="checkbox" class="analysis-components-overwrite" data-panel-key="${escapeHtml(panelKey)}" />
        Overwrite if name exists
      </label>
      <label class="checkbox" title="Abort the copy when any name already exists on the target">
        <input type="checkbox" class="analysis-components-stop" data-panel-key="${escapeHtml(panelKey)}" />
        Stop if name exists on target
      </label>
      <button type="button" class="action analysis-copy-preview-btn" data-panel-key="${escapeHtml(panelKey)}">
        Preview copy plan
      </button>
      <button type="button" class="primary analysis-copy-components-btn" data-panel-key="${escapeHtml(panelKey)}">
        Copy playbook + sub-playbooks + scripts to target
      </button>
    </div>
    <div class="profile-context profile-context-target analysis-components-target-context hidden" aria-live="polite"></div>
    <div class="analysis-copy-binding-preview hidden" aria-live="polite"></div>
    <div class="analysis-copy-result-summary hidden" aria-live="polite"></div>
    <pre class="result analysis-copy-components-result hidden"></pre>
    </section>
  `;
}

function bindAnalysisCopyOptionExclusivity(details) {
  const overwriteEl = details.querySelector(".analysis-components-overwrite");
  const stopEl = details.querySelector(".analysis-components-stop");
  if (!overwriteEl || !stopEl) return;
  overwriteEl.addEventListener("change", () => {
    if (overwriteEl.checked) stopEl.checked = false;
  });
  stopEl.addEventListener("change", () => {
    if (stopEl.checked) overwriteEl.checked = false;
  });
}

function updateAnalysisTargetContext(details) {
  const select = details.querySelector(".analysis-components-target");
  const context = details.querySelector(".analysis-components-target-context");
  if (!select || !context || typeof profileBySlug !== "function" || typeof renderProfileContext !== "function") {
    return;
  }
  const profile = profileBySlug(select.value);
  if (!profile) {
    context.classList.add("hidden");
    context.innerHTML = "";
    return;
  }
  context.classList.remove("hidden");
  context.innerHTML = renderProfileContext(profile, "Copy target");
}

function createAnalysisPanel(data) {
  analysisCounter += 1;
  const panelKey = `analysis-${analysisCounter}-${data.root_playbook.id}`;
  const accordion = document.getElementById("playbooks-analysis-accordion");
  if (!accordion) return null;

  accordion.classList.remove("hidden");
  accordion.querySelectorAll("details.analysis-accordion-item").forEach((item) => {
    item.open = false;
  });

  const details = document.createElement("details");
  details.className = "analysis-accordion-item analysis-panel";
  details.open = true;
  details.id = panelKey;
  details.dataset.sourceProfile = data.profile;
  details.dataset.playbookId = data.root_playbook.id;

  const summary = document.createElement("summary");
  summary.className = "analysis-accordion-summary";
  summary.textContent = `Analysis: ${data.root_playbook.name} (${data.root_playbook.id}) · ${data.profile}`;

  const body = document.createElement("div");
  body.className = "analysis-accordion-body";
  body.innerHTML = buildAnalysisBodyHtml(data, panelKey);

  details.appendChild(summary);
  details.appendChild(body);
  details._analysisData = data;
  accordion.prepend(details);

  const targetSelect = details.querySelector(".analysis-components-target");
  if (targetSelect && typeof populateTargetSelect === "function") {
    populateTargetSelect(targetSelect, data.profile);
    targetSelect.addEventListener("change", () => updateAnalysisTargetContext(details));
    updateAnalysisTargetContext(details);
  }

  bindAnalysisCopyOptionExclusivity(details);
  bindAnalysisHelp(details);
  bindAnalysisSectionNav(details, panelKey);
  bindRefactorPanel(details, data);
  bindFlowGraphNav(details, data, panelKey);
  bindStructureTreeNavigation(details);
  bindPlaybookTaskListingLinks(details, panelKey);

  details.querySelector(".analysis-copy-preview-btn")?.addEventListener("click", () => {
    void previewCopyPlanForPanel(details, data);
  });
  details.querySelector(".analysis-copy-components-btn")?.addEventListener("click", () => {
    copyPlaybookComponentsForPanel(details, data);
  });

  details.addEventListener("toggle", () => {
    if (!details.open) return;
    accordion.querySelectorAll("details.analysis-accordion-item").forEach((item) => {
      if (item !== details) item.open = false;
    });
  });

  return details;
}

function refillAnalysisCopyTargets() {
  document.querySelectorAll(".analysis-components-target").forEach((select) => {
    const exclude = select.dataset.sourceProfile || "";
    if (typeof populateTargetSelect === "function") {
      populateTargetSelect(select, exclude);
    }
    const details = select.closest("details.analysis-accordion-item");
    if (details) updateAnalysisTargetContext(details);
  });
}

window.refillAnalysisCopyTargets = refillAnalysisCopyTargets;

async function analyzeSelectedPlaybook() {
  const selected = selectedPlaybookRows();
  if (selected.length !== 1) {
    alert("Select exactly one playbook to analyze.");
    return;
  }
  const profile = document.getElementById("active-profile").value;
  const playbookId = selected[0].id;
  try {
    const data = await withLoader(
      () => api(`/api/playbooks/${encodeURIComponent(playbookId)}/analysis?profile=${encodeURIComponent(profile)}`),
      "Analyzing playbook…",
    );
    createAnalysisPanel(data);
  } catch (err) {
    alert(`Analysis failed: ${err.message}`);
  }
}

function formatActionList(items, idKey, emptyLabel) {
  if (!items?.length) {
    return [emptyLabel];
  }
  return items.map((item) => `  · ${item.name || item[idKey] || "?"} [${item.action}]`);
}

function formatIntegrationCommands(commands, maxRows = 12) {
  if (!commands?.length) {
    return ["  (none in this playbook tree)"];
  }
  const lines = commands.slice(0, maxRows).map((row) => `  · ${row.command} (×${row.count})`);
  if (commands.length > maxRows) {
    lines.push(`  … and ${commands.length - maxRows} more`);
  }
  return lines;
}

function formatComponentsPlanSummary(plan, analysisData) {
  const integrationCommands =
    plan.integration_commands_used ||
    analysisData?.integration_commands_used ||
    analysisData?.commands_used ||
    [];
  const lines = [
    `Copy playbook components from ${plan.source_profile} to ${plan.target_profile}?`,
    "",
    `Root playbook: ${plan.root_playbook_name}`,
    "",
    "WILL BE COPIED",
    "Playbooks (sub-playbooks first, then root):",
    ...formatActionList(plan.playbooks?.items, "playbook_id", "  (none)"),
    "",
    "Automation scripts (custom scripts uploaded as YAML):",
    ...formatActionList(plan.scripts?.items, "script_id", "  (none)"),
    "",
    "WILL NOT BE COPIED",
    "Integration commands (Brand|||command — tenant must provide these):",
    ...formatIntegrationCommands(integrationCommands),
    "",
    "The target tenant must have the same integrations configured.",
    "Only custom automation scripts are copied; built-in integration commands are not.",
  ];
  if (plan.warnings?.length) {
    lines.push("", "Warnings:", ...plan.warnings.map((w) => `  - ${w}`));
  }
  if (plan.missing_sub_playbooks?.length) {
    lines.push("", "Missing sub-playbooks (copy will abort):");
    plan.missing_sub_playbooks.forEach((item) => lines.push(`  - ${item.lookup_key}`));
  }
  lines.push(
    "",
    `Summary — scripts: copy ${plan.scripts.counts.copy}, update ${plan.scripts.counts.update}, skip ${plan.scripts.counts.skip}`,
    `Summary — playbooks: copy ${plan.playbooks.counts.copy}, update ${plan.playbooks.counts.update}, skip ${plan.playbooks.counts.skip}`,
    "",
    plan.would_abort ? "No action will be taken (conflict)." : "Proceed with copy?",
  );
  return lines.join("\n");
}

async function copyPlaybookComponentsForPanel(details, data) {
  const source = data.profile;
  const target = details.querySelector(".analysis-components-target")?.value;
  if (!target) {
    alert("Choose a target profile.");
    return;
  }

  const payload = {
    source_profile: source,
    target_profile: target,
    playbook_id: data.root_playbook.id,
    overwrite: details.querySelector(".analysis-components-overwrite")?.checked ?? false,
    stop_on_conflict: details.querySelector(".analysis-components-stop")?.checked ?? false,
  };
  const resultEl = details.querySelector(".analysis-copy-components-result");

  try {
    const plan = await withLoader(
      () =>
        api("/api/playbooks/copy-components/preview", {
          method: "POST",
          body: JSON.stringify(payload),
        }),
      "Planning component copy…",
    );

    if (plan.would_abort || plan.missing_sub_playbooks?.length) {
      alert(formatComponentsPlanSummary(plan, data));
      return;
    }

    const proceedCopy =
      typeof showConfirmDialog === "function"
        ? await showConfirmDialog({
            title: "Confirm deep copy",
            message: formatComponentsPlanSummary(plan, data),
            proceedLabel: "Copy components",
          })
        : window.confirm(formatComponentsPlanSummary(plan, data));
    if (!proceedCopy) {
      return;
    }

    const copyResult = await withLoader(
      () =>
        api("/api/playbooks/copy-components", {
          method: "POST",
          body: JSON.stringify(payload),
        }),
      "Copying playbook components…",
    );
    resultEl.textContent = JSON.stringify(copyResult, null, 2);
    resultEl.classList.remove("hidden");
    renderCopyResultSummary(details.querySelector(".analysis-copy-result-summary"), copyResult);
    if (typeof showOutcomeDialog === "function" && typeof summarizeComponentCopyResult === "function") {
      showOutcomeDialog(summarizeComponentCopyResult(copyResult));
    } else if (copyResult.aborted) {
      alert(copyResult.reason || "Copy was aborted.");
    }
  } catch (err) {
    if (typeof showOutcomeDialog === "function") {
      showOutcomeDialog({ title: "Deep copy failed", message: err.message, success: false });
    } else {
      alert(`Copy failed: ${err.message}`);
    }
  }
}

const REFACTOR_OP_LABELS = {
  leaf: "Leaf extract",
  cluster: "Cluster extract",
  error: "Error handling",
};

let refactorErrorOpCounter = 0;

function resolveAnalysisDataForPanel(panel) {
  return panel?.closest("details.analysis-panel")?._analysisData || null;
}

function getRefactorTaskCatalog(data) {
  return Array.isArray(data?.refactor_task_catalog) ? data.refactor_task_catalog : [];
}

function compareRefactorTaskIds(a, b) {
  const textA = String(a);
  const textB = String(b);
  const keyA = /^\d+$/.test(textA) ? [0, textA.padStart(20, "0")] : [1, textA];
  const keyB = /^\d+$/.test(textB) ? [0, textB.padStart(20, "0")] : [1, textB];
  if (keyA[0] !== keyB[0]) {
    return keyA[0] - keyB[0];
  }
  return keyA[1].localeCompare(keyB[1]);
}

function refactorTaskOptionLabel(entry) {
  const parts = [`#${entry.id}`, entry.label || "—"];
  const detail = entry.description_short || entry.description || entry.task_type || "";
  if (detail) {
    parts.push(detail);
  }
  return parts.join(" · ");
}

function sortRefactorCatalog(catalog) {
  return [...catalog].sort((a, b) => compareRefactorTaskIds(a.id, b.id));
}

function catalogWithExtraTask(catalog, taskId, label = "") {
  const id = String(taskId || "").trim();
  if (!id || catalog.some((entry) => String(entry.id) === id)) {
    return catalog;
  }
  return [
    ...catalog,
    {
      id,
      label: label || id,
      task_type: "unknown",
      leaf_ok: false,
      leaf_reasons: ["Task not found in analysis catalog — re-run analysis if the playbook changed"],
    },
  ];
}

function parseClusterSpec(value) {
  const text = String(value || "").trim();
  const match = text.match(/^\s*(\d+)\s*:\s*(\d+)\s*$/);
  if (!match) {
    return { start: "", end: "" };
  }
  return { start: match[1], end: match[2] };
}

function buildRefactorTaskSelectHtml(catalog, selectedId, selectClass, placeholder) {
  const options = [`<option value="">${escapeHtml(placeholder)}</option>`];
  for (const entry of sortRefactorCatalog(catalog)) {
    const isSelected = String(entry.id) === String(selectedId);
    const selected = isSelected ? " selected" : "";
    const tooltip = [entry.label, entry.description_short || entry.description, entry.task_type]
      .filter(Boolean)
      .join(" — ");
    options.push(
      `<option value="${escapeHtml(entry.id)}"${selected} title="${escapeHtml(tooltip)}">${escapeHtml(refactorTaskOptionLabel(entry))}</option>`,
    );
  }
  return `<select class="${selectClass}">${options.join("")}</select>`;
}

function collectLeafTaskIdsFromPanel(panel) {
  return [...panel.querySelectorAll('.refactor-op-row[data-op-type="leaf"]')]
    .map((row) => row.querySelector(".refactor-leaf-task")?.value.trim() || "")
    .filter(Boolean);
}

function setRefactorOpValidation(row, { ok, message }) {
  const validation = row.querySelector(".refactor-op-validation");
  if (!validation) {
    return;
  }
  validation.textContent = message;
  validation.classList.remove("hidden", "refactor-op-validation-ok", "refactor-op-validation-pending");
  if (ok === true) {
    validation.classList.add("refactor-op-validation-ok");
    row.classList.remove("refactor-op-invalid");
  } else if (ok === false) {
    row.classList.add("refactor-op-invalid");
  } else {
    validation.classList.add("refactor-op-validation-pending");
    row.classList.remove("refactor-op-invalid");
  }
}

async function checkRefactorOpValidity(row, panel, analysisData) {
  const data = analysisData || resolveAnalysisDataForPanel(panel);
  const profile = data?.profile || document.getElementById("active-profile")?.value || "";
  const playbookId = data?.root_playbook?.id || "";
  const type = row.dataset.opType;

  if (!profile || !playbookId) {
    setRefactorOpValidation(row, { ok: false, message: "Analysis context missing — re-run analysis." });
    return;
  }

  let payload;
  if (type === "leaf") {
    const taskId = row.querySelector(".refactor-leaf-task")?.value.trim() || "";
    if (!taskId) {
      setRefactorOpValidation(row, { ok: false, message: "Select a task first." });
      return;
    }
    const otherLeaf = collectLeafTaskIdsFromPanel(panel).filter((id) => id !== taskId);
    payload = { profile, playbook_id: playbookId, kind: "leaf", task_id: taskId, other_leaf_tasks: otherLeaf };
  } else if (type === "cluster") {
    const spec = row.querySelector(".refactor-cluster-spec")?.value.trim();
    let start = "";
    let end = "";
    if (spec) {
      ({ start, end } = parseClusterSpec(spec));
    } else {
      start = row.querySelector(".refactor-cluster-start")?.value.trim() || "";
      end = row.querySelector(".refactor-cluster-end")?.value.trim() || "";
    }
    if (!start || !end) {
      setRefactorOpValidation(row, { ok: false, message: "Select both start and end tasks." });
      return;
    }
    payload = { profile, playbook_id: playbookId, kind: "cluster", start_id: start, end_id: end };
  } else {
    return;
  }

  setRefactorOpValidation(row, { ok: null, message: "Checking…" });
  try {
    const result = await api("/api/playbooks/refactor/validate-extract", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (result.ok) {
      const detail =
        type === "cluster" && result.cluster_task_ids?.length
          ? `Valid cluster (${result.cluster_task_ids.length} task(s): ${result.cluster_task_ids.join(", ")})`
          : "Valid for extract.";
      setRefactorOpValidation(row, { ok: true, message: detail });
    } else {
      const reasons = Array.isArray(result.reasons) ? result.reasons : ["Invalid selection."];
      setRefactorOpValidation(row, { ok: false, message: reasons.join(" ") });
    }
  } catch (err) {
    setRefactorOpValidation(row, { ok: false, message: err.message || String(err) });
  }
}

function parsePostTaskUpdateSpec(spec) {
  const text = String(spec || "").trim();
  const pipe = text.indexOf("|");
  if (pipe < 0) {
    throw new Error("Must look like MATCH|actions (example: contains:HttpV2:i|retry=30x30,stop-on-error)");
  }
  const matchPart = text.slice(0, pipe).trim();
  const actionsPart = text.slice(pipe + 1).trim();
  if (!matchPart || !actionsPart) {
    throw new Error("Missing match pattern or actions");
  }

  let caseInsensitive = false;
  let matchText = matchPart;
  if (matchText.endsWith(":i")) {
    caseInsensitive = true;
    matchText = matchText.slice(0, -2);
  }

  let matchMode = "contains";
  let pattern = matchText;
  if (matchText.startsWith("contains:")) {
    pattern = matchText.slice("contains:".length);
  } else if (matchText.startsWith("equals:")) {
    matchMode = "equals";
    pattern = matchText.slice("equals:".length);
  }
  if (!pattern) {
    throw new Error("Match pattern is required");
  }

  const state = {
    matchMode,
    pattern,
    caseInsensitive,
    retryMode: "none",
    retryCount: "",
    retryInterval: "",
    errorHandling: "",
  };

  for (const rawAction of actionsPart.split(",")) {
    const action = rawAction.trim();
    if (!action) continue;
    if (action === "clear-retry") {
      state.retryMode = "clear";
    } else if (action === "stop-on-error" || action === "continue" || action === "error-path") {
      state.errorHandling = action;
    } else if (action.startsWith("retry=")) {
      const payload = action.slice("retry=".length);
      const xIndex = payload.indexOf("x");
      if (xIndex < 0) {
        throw new Error(`Retry must look like retry=NxI (got ${action})`);
      }
      state.retryMode = "set";
      state.retryCount = payload.slice(0, xIndex);
      state.retryInterval = payload.slice(xIndex + 1);
    } else {
      throw new Error(`Unknown action: ${action}`);
    }
  }
  return state;
}

function readErrorHandlingRow(row) {
  const matchMode = row.querySelector(".refactor-error-match-mode")?.value || "contains";
  const pattern = row.querySelector(".refactor-error-pattern")?.value.trim() || "";
  const caseInsensitive = row.querySelector(".refactor-error-case-insensitive")?.checked === true;
  const retryMode = row.querySelector(".refactor-error-retry-mode:checked")?.value || "none";
  const retryCount = row.querySelector(".refactor-error-retry-count")?.value.trim() || "";
  const retryInterval = row.querySelector(".refactor-error-retry-interval")?.value.trim() || "";
  const errorHandling = row.querySelector(".refactor-error-handling")?.value || "";
  return { matchMode, pattern, caseInsensitive, retryMode, retryCount, retryInterval, errorHandling };
}

function composePostTaskUpdateSpec(state) {
  if (!state.pattern) {
    throw new Error("Task title pattern is required");
  }
  let matchPart = `${state.matchMode}:${state.pattern}`;
  if (state.caseInsensitive) {
    matchPart += ":i";
  }
  const actions = [];
  if (state.retryMode === "clear") {
    actions.push("clear-retry");
  } else if (state.retryMode === "set") {
    const count = Number(state.retryCount);
    const interval = Number(state.retryInterval);
    if (!Number.isFinite(count) || count <= 0) {
      throw new Error("Retry count must be a positive number");
    }
    if (!Number.isFinite(interval) || interval <= 0) {
      throw new Error("Retry interval (seconds) must be a positive number");
    }
    actions.push(`retry=${count}x${interval}`);
  }
  if (state.errorHandling) {
    actions.push(state.errorHandling);
  }
  if (!actions.length) {
    throw new Error("Choose at least one change: retry, clear retry, or on-error behaviour");
  }
  return `${matchPart}|${actions.join(",")}`;
}

function validateLeafTaskValue(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "Task id or name is required";
  }
  return null;
}

function validateClusterValue(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "Cluster range is required";
  }
  const match = text.match(/^\s*(\d+)\s*:\s*(\d+)\s*$/);
  if (!match) {
    return "Cluster must look like START:END (e.g. 21:52)";
  }
  if (Number(match[1]) >= Number(match[2])) {
    return "START must be less than END";
  }
  return null;
}

function updateErrorHandlingRowPreview(row) {
  const preview = row.querySelector(".refactor-error-spec-preview");
  const validation = row.querySelector(".refactor-error-validation");
  try {
    const spec = composePostTaskUpdateSpec(readErrorHandlingRow(row));
    if (preview) {
      preview.textContent = spec;
    }
    validation?.classList.add("hidden");
    row.classList.remove("refactor-op-invalid");
    return spec;
  } catch (err) {
    if (preview) {
      preview.textContent = "";
    }
    if (validation) {
      validation.textContent = err.message || String(err);
      validation.classList.remove("hidden");
    }
    row.classList.add("refactor-op-invalid");
    return null;
  }
}

function describePlannedErrorHandlingChanges(state) {
  const parts = [];
  if (state.retryMode === "clear") {
    parts.push("Clear retry");
  } else if (state.retryMode === "set") {
    parts.push(`Set retry ${state.retryCount}× every ${state.retryInterval}s`);
  }
  if (state.errorHandling === "stop-on-error") {
    parts.push("Stop playbook on error");
  } else if (state.errorHandling === "continue") {
    parts.push("Continue on error");
  } else if (state.errorHandling === "error-path") {
    parts.push("Use error path");
  }
  return parts.length ? parts.join(" · ") : "No changes selected";
}

function formatErrorHandlingLabel(value) {
  if (value === "error-path") return "Error path";
  if (value === "continue") return "Continue";
  if (value === "stop") return "Stop";
  return value || "—";
}

function renderErrorHandlingMatchPreview(row, analysisData, matches, matchState, plannedChanges) {
  const host = row.querySelector(".refactor-error-match-preview");
  if (!host) {
    return;
  }
  const modeLabel = matchState.matchMode === "equals" ? "equals" : "contains";
  const caseLabel = matchState.caseInsensitive ? " · ignore case" : "";
  const header =
    `Match preview: ${matches.length} regular script task(s) ` +
    `(${modeLabel} “${matchState.pattern}”${caseLabel}). ` +
    `Searches playbooks in this analysis. After refactor, updates apply to generated sub-playbooks.`;

  if (!matches.length) {
    host.innerHTML =
      `<p class="meta">${escapeHtml(header)}</p>` +
      `<p class="meta">No matching tasks found.</p>` +
      `<p class="meta">Planned changes if matched: ${escapeHtml(plannedChanges)}</p>`;
    host.classList.remove("hidden");
    return;
  }

  const rows = matches.map((match) => {
    const location = `${match.playbook_role === "root" ? "Root" : "Sub"} · ${match.playbook_name}`;
    const reachable = match.reachable ? "Yes" : "No";
    const errorPath = match.has_error_path ? "Yes" : "No";
    return [
      location,
      match.task_id,
      match.title,
      match.script_name || match.script_binding || "—",
      reachable,
      match.retry_label,
      formatErrorHandlingLabel(match.error_handling),
      errorPath,
    ];
  });

  host.innerHTML =
    `<p class="meta">${escapeHtml(header)}</p>` +
    `<p class="meta">Planned changes if matched: ${escapeHtml(plannedChanges)}</p>` +
    renderAnalysisTableHtml(
      ["Location", "Task #", "Title", "Script", "Reachable", "Current retry", "On error", "Error path"],
      rows,
    );
  host.classList.remove("hidden");
}

function refreshErrorHandlingMatchPreview(row, analysisData) {
  const host = row.querySelector(".refactor-error-match-preview");
  try {
    const matchState = readErrorHandlingRow(row);
    if (!matchState.pattern) {
      if (host) {
        host.innerHTML = '<p class="meta">Enter a match pattern, then click Refresh preview.</p>';
        host.classList.remove("hidden");
      }
      return;
    }
    composePostTaskUpdateSpec(matchState);
    const plannedChanges = describePlannedErrorHandlingChanges(matchState);
    if (!window.RefactorGraphValidation?.findErrorHandlingMatches) {
      if (host) {
        host.textContent = "Match preview unavailable (validation script not loaded).";
        host.classList.remove("hidden");
      }
      return;
    }
    const matches = RefactorGraphValidation.findErrorHandlingMatches(analysisData, matchState);
    renderErrorHandlingMatchPreview(row, analysisData, matches, matchState, plannedChanges);
  } catch (err) {
    if (host) {
      host.innerHTML = `<p class="meta refactor-error-validation">Cannot preview matches: ${escapeHtml(err.message || String(err))}</p>`;
      host.classList.remove("hidden");
    }
  }
}

function bindErrorHandlingRow(row, analysisData = null) {
  const refreshSpec = () => updateErrorHandlingRowPreview(row);
  row.querySelectorAll("input, select").forEach((input) => {
    input.addEventListener("change", refreshSpec);
    input.addEventListener("input", refreshSpec);
  });
  refreshSpec();
  row.querySelector(".refactor-error-refresh-matches-btn")?.addEventListener("click", () => {
    const data = analysisData || resolveAnalysisDataForPanel(row.closest(".refactor-panel"));
    refreshErrorHandlingMatchPreview(row, data);
  });
}

function errorHandlingOpRowHtml(initial = {}) {
  const rowId = `err-${++refactorErrorOpCounter}`;
  const matchMode = initial.matchMode || "contains";
  const pattern = initial.pattern || "";
  const caseInsensitive = initial.caseInsensitive ? " checked" : "";
  const retryMode = initial.retryMode || "none";
  const retryCount = initial.retryCount || "";
  const retryInterval = initial.retryInterval || "";
  const errorHandling = initial.errorHandling || "";
  return (
    `<div class="refactor-op-row refactor-op-error" data-op-type="error">` +
    `<div class="refactor-op-header">` +
    `<span class="refactor-op-kind">${escapeHtml(REFACTOR_OP_LABELS.error)} ${analysisHelpButton(
      "Apply retry and on-error settings to regular script tasks in generated sub-playbooks (after compare passes).",
      "<p><strong>Match</strong> — task title contains or equals a pattern (regular script tasks only). " +
        "<strong>Retry</strong> — sets <code>retry-count</code> and <code>retry-interval</code> script arguments. " +
        "<strong>On error</strong> — stop playbook, continue anyway, or follow the #error# branch.</p>",
    )}</span>` +
    `<button type="button" class="danger refactor-op-remove" title="Remove operation">Remove</button>` +
    `</div>` +
    `<div class="refactor-error-fields">` +
    `<section class="refactor-error-section">` +
    `<h4 class="refactor-error-section-title">1. Match tasks</h4>` +
    `<p class="meta refactor-error-section-lead">Regular script tasks whose title matches this pattern (searches the analysis tree).</p>` +
    `<div class="refactor-error-row">` +
    `<label>Title` +
    `<select class="refactor-error-match-mode">` +
    `<option value="contains"${matchMode === "contains" ? " selected" : ""}>contains</option>` +
    `<option value="equals"${matchMode === "equals" ? " selected" : ""}>equals</option>` +
    `</select></label>` +
    `<label class="refactor-error-pattern-label">Pattern` +
    `<input type="text" class="refactor-error-pattern" placeholder="e.g. HttpV2" value="${escapeHtml(pattern)}" /></label>` +
    `<label class="refactor-error-case"><input type="checkbox" class="refactor-error-case-insensitive"${caseInsensitive} /> Ignore case</label>` +
    `</div>` +
    `</section>` +
    `<section class="refactor-error-section">` +
    `<h4 class="refactor-error-section-title">2. Retry ${analysisHelpButton("Optional. Sets retry-count and retry-interval on matched script tasks.")}</h4>` +
    `<fieldset class="refactor-error-retry">` +
    `<label class="refactor-error-choice"><input type="radio" class="refactor-error-retry-mode" name="retry-${rowId}" value="none"${retryMode === "none" ? " checked" : ""} /> No retry change</label>` +
    `<label class="refactor-error-choice"><input type="radio" class="refactor-error-retry-mode" name="retry-${rowId}" value="set"${retryMode === "set" ? " checked" : ""} /> Set retry</label>` +
    `<label class="refactor-error-retry-set">Count <input type="number" class="refactor-error-retry-count" min="1" placeholder="30" value="${escapeHtml(String(retryCount))}" /></label>` +
    `<label class="refactor-error-retry-set">Interval (s) <input type="number" class="refactor-error-retry-interval" min="1" placeholder="30" value="${escapeHtml(String(retryInterval))}" /></label>` +
    `<label class="refactor-error-choice"><input type="radio" class="refactor-error-retry-mode" name="retry-${rowId}" value="clear"${retryMode === "clear" ? " checked" : ""} /> Clear retry</label>` +
    `</fieldset>` +
    `</section>` +
    `<section class="refactor-error-section">` +
    `<h4 class="refactor-error-section-title">3. On error</h4>` +
    `<label class="refactor-error-handling-label">Behaviour` +
    `<select class="refactor-error-handling">` +
    `<option value=""${!errorHandling ? " selected" : ""}>— no change —</option>` +
    `<option value="stop-on-error"${errorHandling === "stop-on-error" ? " selected" : ""}>Stop playbook</option>` +
    `<option value="continue"${errorHandling === "continue" ? " selected" : ""}>Continue (ignore error)</option>` +
    `<option value="error-path"${errorHandling === "error-path" ? " selected" : ""}>Use error path (#error#)</option>` +
    `</select></label>` +
    `</section>` +
    `<div class="refactor-error-spec-box">` +
    `<span class="refactor-error-spec-label">Generated spec</span>` +
    `<code class="refactor-error-spec-preview"></code>` +
    `</div>` +
    `<div class="refactor-error-validation meta hidden"></div>` +
    `<section class="refactor-error-section refactor-error-preview-section">` +
    `<h4 class="refactor-error-section-title">Match preview</h4>` +
    `<div class="refactor-error-match-actions">` +
    `<button type="button" class="action refactor-error-refresh-matches-btn">Refresh match preview</button>` +
    `<span class="meta">Not live — refresh after editing match rules.</span>` +
    `</div>` +
    `<div class="refactor-error-match-preview hidden" aria-live="polite"></div>` +
    `</section>` +
    `</div>` +
    `</div>`
  );
}

function refactorOpRowHtml(type, value = "", analysisData = null) {
  const label = REFACTOR_OP_LABELS[type] || type;
  if (type === "error") {
    try {
      return errorHandlingOpRowHtml(parsePostTaskUpdateSpec(value));
    } catch {
      return errorHandlingOpRowHtml({ pattern: value });
    }
  }

  const catalog = sortRefactorCatalog(getRefactorTaskCatalog(analysisData));
  const useDropdowns = catalog.length > 0;

  let field = "";
  const leafHelp = analysisHelpButton(
    "Leaf extract root task. Must be a potential root: no self-loops and no outside incoming edges into its descendant subtree (except allowed orphan feeders).",
  );
  const clusterStartHelp = analysisHelpButton("First task in the cluster (inclusive).");
  const clusterEndHelp = analysisHelpButton(
    "Last task in the cluster (inclusive). Must be reachable from start; must not be a condition task.",
  );

  if (type === "leaf") {
    if (useDropdowns) {
      const selected = String(value || "").trim();
      const enriched = catalogWithExtraTask(catalog, selected);
      field =
        `<div class="refactor-op-body">` +
        `<label class="refactor-op-task-label">Task ${leafHelp}` +
        `${buildRefactorTaskSelectHtml(enriched, selected, "refactor-leaf-task", "— select task —")}</label>` +
        `<button type="button" class="secondary refactor-check-validity-btn">Check validity</button>` +
        `<div class="refactor-op-validation meta hidden" aria-live="polite"></div>` +
        `</div>`;
    } else {
      field =
        `<div class="refactor-op-body">` +
        `<label>Task id ${analysisHelpButton("Numeric task id from the root playbook.")}` +
        `<input type="text" class="refactor-op-value refactor-leaf-task" placeholder="e.g. 366" value="${escapeHtml(value)}" /></label>` +
        `<button type="button" class="secondary refactor-check-validity-btn">Check validity</button>` +
        `<div class="refactor-op-validation meta hidden" aria-live="polite"></div>` +
        `</div>`;
    }
  } else if (type === "cluster") {
    const { start, end } = parseClusterSpec(value);
    if (useDropdowns) {
      const enriched = catalogWithExtraTask(catalogWithExtraTask(catalog, start), end);
      field =
        `<div class="refactor-op-body">` +
        `<div class="refactor-cluster-fields">` +
        `<label>Start ${clusterStartHelp}` +
        `${buildRefactorTaskSelectHtml(enriched, start, "refactor-cluster-start", "— start —")}</label>` +
        `<label>End ${clusterEndHelp}` +
        `${buildRefactorTaskSelectHtml(enriched, end, "refactor-cluster-end", "— end —")}</label>` +
        `</div>` +
        `<button type="button" class="secondary refactor-check-validity-btn">Check validity</button>` +
        `<div class="refactor-op-validation meta hidden" aria-live="polite"></div>` +
        `</div>`;
    } else {
      field =
        `<div class="refactor-op-body">` +
        `<label>Cluster START:END ${analysisHelpButton("Inclusive task id range (e.g. 21:52).")}` +
        `<input type="text" class="refactor-op-value refactor-cluster-spec" placeholder="e.g. 21:52" value="${escapeHtml(value)}" /></label>` +
        `<button type="button" class="secondary refactor-check-validity-btn">Check validity</button>` +
        `<div class="refactor-op-validation meta hidden" aria-live="polite"></div>` +
        `</div>`;
    }
  }

  return (
    `<div class="refactor-op-row refactor-op-${escapeHtml(type)}" data-op-type="${escapeHtml(type)}">` +
    `<div class="refactor-op-header">` +
    `<span class="refactor-op-kind">${escapeHtml(label)}</span>` +
    `<button type="button" class="danger refactor-op-remove" title="Remove operation">Remove</button>` +
    `</div>` +
    field +
    `</div>`
  );
}

function bindLeafClusterOpRow(row, panel, analysisData) {
  row.querySelector(".refactor-check-validity-btn")?.addEventListener("click", () => {
    void checkRefactorOpValidity(row, panel, analysisData);
  });
  row.querySelector(".refactor-op-remove")?.addEventListener("click", () => {
    row.remove();
  });
  row.querySelectorAll(".refactor-leaf-task, .refactor-cluster-start, .refactor-cluster-end, .refactor-op-value").forEach((input) => {
    input.addEventListener("change", () => {
      setRefactorOpValidation(row, { ok: null, message: "Selection changed — check validity again." });
    });
  });
}

function addRefactorOperation(panel, type, value = "", analysisData = null) {
  const list = panel.querySelector(".refactor-ops-list");
  if (!list) return;
  const data = analysisData || resolveAnalysisDataForPanel(panel);
  const wrapper = document.createElement("div");
  wrapper.innerHTML = refactorOpRowHtml(type, value, data);
  const row = wrapper.firstElementChild;
  if (type === "error") {
    row.querySelector(".refactor-op-remove")?.addEventListener("click", () => row.remove());
    bindErrorHandlingRow(row, data);
    bindAnalysisHelp(row);
  } else {
    bindLeafClusterOpRow(row, panel, data);
    bindAnalysisHelp(row);
  }
  list.appendChild(row);
}

function collectRefactorOperations(panel) {
  const leaf_tasks = [];
  const clusters = [];
  const post_task_updates = [];
  panel.querySelectorAll(".refactor-op-row").forEach((row) => {
    const type = row.dataset.opType;
    if (type === "leaf") {
      const value =
        row.querySelector(".refactor-leaf-task")?.value.trim() ||
        row.querySelector(".refactor-op-value")?.value.trim() ||
        "";
      if (value) leaf_tasks.push(value);
    } else if (type === "cluster") {
      const spec = row.querySelector(".refactor-cluster-spec")?.value.trim();
      if (spec) {
        clusters.push(spec);
      } else {
        const start = row.querySelector(".refactor-cluster-start")?.value.trim() || "";
        const end = row.querySelector(".refactor-cluster-end")?.value.trim() || "";
        if (start && end) clusters.push(`${start}:${end}`);
      }
    } else if (type === "error") {
      const spec = updateErrorHandlingRowPreview(row);
      if (spec) post_task_updates.push(spec);
    }
  });
  return { leaf_tasks, clusters, post_task_updates };
}

function validateRefactorOperations(panel) {
  const errors = [];

  panel.querySelectorAll('.refactor-op-row[data-op-type="leaf"]').forEach((row, index) => {
    const value = row.querySelector(".refactor-leaf-task, .refactor-op-value")?.value.trim() || "";
    if (!value) {
      errors.push(`${REFACTOR_OP_LABELS.leaf} #${index + 1}: Select a task`);
      return;
    }
    const leafError = validateLeafTaskValue(value);
    if (leafError) {
      errors.push(`${REFACTOR_OP_LABELS.leaf} #${index + 1}: ${leafError}`);
    }
  });

  panel.querySelectorAll('.refactor-op-row[data-op-type="cluster"]').forEach((row, index) => {
    const spec = row.querySelector(".refactor-cluster-spec")?.value.trim();
    let start = "";
    let end = "";
    if (spec) {
      ({ start, end } = parseClusterSpec(spec));
    } else {
      start = row.querySelector(".refactor-cluster-start")?.value.trim() || "";
      end = row.querySelector(".refactor-cluster-end")?.value.trim() || "";
    }
    if (!start || !end) {
      errors.push(`${REFACTOR_OP_LABELS.cluster} #${index + 1}: Select both start and end tasks`);
      return;
    }
    const clusterError = validateClusterValue(spec || `${start}:${end}`);
    if (clusterError) {
      errors.push(`${REFACTOR_OP_LABELS.cluster} #${index + 1}: ${clusterError}`);
    }
  });

  panel.querySelectorAll('.refactor-op-row[data-op-type="error"]').forEach((row, index) => {
    try {
      composePostTaskUpdateSpec(readErrorHandlingRow(row));
    } catch (err) {
      errors.push(`${REFACTOR_OP_LABELS.error} #${index + 1}: ${err.message || String(err)}`);
    }
  });

  return errors;
}

function refactorPayloadFromPanel(details, data) {
  const panel = details.querySelector(".refactor-panel");
  const ops = collectRefactorOperations(panel);
  const parentCopyName = panel?.querySelector(".refactor-parent-copy-name")?.value.trim() || undefined;
  const parallel = panel?.querySelector(".refactor-parallel-checkbox")?.checked === true;
  const payload = {
    profile: data.profile,
    playbook_id: data.root_playbook.id,
    leaf_tasks: ops.leaf_tasks,
    clusters: ops.clusters,
    post_task_updates: ops.post_task_updates,
    parent_copy_name: parentCopyName || undefined,
  };
  if (parallel) {
    payload.refactor_mode = "parallel";
  }
  return payload;
}

function formatRefactorPreview(plan) {
  const lines = [
    `Refactor preflight for ${plan.source_playbook?.name || plan.source_playbook?.id || "playbook"}`,
    plan.ok ? "Status: OK" : "Status: FAILED",
  ];
  if (plan.reasons?.length) {
    lines.push("", "Issues:", ...plan.reasons.map((item) => `  - ${item}`));
  }
  lines.push("", `Parent copy: ${plan.parent_copy_name || "—"}`);
  if (plan.extractions?.length) {
    lines.push("", "Planned extractions:");
    plan.extractions.forEach((row) => {
      if (row.kind === "cluster") {
        lines.push(`  · cluster ${row.start_task_id}:${row.end_task_id} → ${row.subplaybook_name}`);
      } else {
        lines.push(`  · leaf ${row.task_id} (${row.task_label}) → ${row.subplaybook_name}`);
      }
    });
  }
  if (plan.post_task_updates?.length) {
    lines.push("", "Post-refactor task updates:");
    plan.post_task_updates.forEach((spec) => lines.push(`  · ${spec}`));
  }
  return lines.join("\n");
}

function ensureRefactorPanelValid(panel) {
  const validationErrors = validateRefactorOperations(panel);
  if (validationErrors.length) {
    alert(`Fix refactor operations before continuing:\n\n${validationErrors.join("\n")}`);
    return false;
  }
  if (panel?.querySelector('.refactor-op-row[data-op-type="error"].refactor-op-invalid')) {
    alert("Fix invalid error-handling operations (highlighted in red) before continuing.");
    return false;
  }
  return true;
}

async function previewRefactorForPanel(details, data) {
  const panel = details.querySelector(".refactor-panel");
  const resultEl = panel?.querySelector(".refactor-result");
  if (!ensureRefactorPanelValid(panel)) {
    return;
  }
  const payload = refactorPayloadFromPanel(details, data);
  if (!payload.leaf_tasks.length && !payload.clusters.length) {
    alert("Add at least one leaf or cluster extract operation.");
    return;
  }
  try {
    const plan = await withLoader(
      () =>
        api("/api/playbooks/refactor/preview", {
          method: "POST",
          body: JSON.stringify(payload),
        }),
      "Preflight refactor…",
    );
    if (resultEl) {
      resultEl.textContent = JSON.stringify(plan, null, 2);
      resultEl.classList.remove("hidden");
    }
    alert(formatRefactorPreview(plan));
  } catch (err) {
    alert(`Refactor preview failed: ${err.message}`);
  }
}

const REFACTOR_PROGRESS_PHASE_LABELS = {
  "workflow.start": "Workflow",
  "workflow.complete": "Workflow",
  "workflow.failed": "Workflow",
  "clear.start": "Clear",
  "clear.complete": "Clear",
  "refactor.start": "Refactor",
  "refactor.complete": "Refactor",
  "refactor.failed": "Refactor",
  "refactor.parallel.start": "Parallel",
  "refactor.parallel.complete": "Parallel",
  "refactor.progress": "Progress",
  start: "Start",
  complete: "Complete",
  log: "Log",
};

function refactorProgressLevel(event) {
  const phase = String(event?.phase || "");
  if (phase.includes("failed") || event?.ok === false) {
    return "error";
  }
  if (phase.includes("complete") || event?.ok === true) {
    return "success";
  }
  return "info";
}

function normalizeRefactorProgressEvent(event) {
  if (typeof event === "string") {
    return { phase: "log", phaseLabel: "Log", message: event, level: "info" };
  }
  const phase = String(event?.phase || event?.message || "log");
  const phaseLabel = REFACTOR_PROGRESS_PHASE_LABELS[phase] || phase;
  const parts = [];
  if (event?.step_id) {
    parts.push(`[${event.step_id}]`);
  }
  if (event?.message) {
    parts.push(String(event.message));
  } else if (event?.phase) {
    parts.push(String(event.phase));
  }
  if (event?.elapsed_ms != null) {
    parts.push(`(${event.elapsed_ms} ms)`);
  }
  return {
    phase,
    phaseLabel,
    message: parts.join(" ") || JSON.stringify(event),
    level: refactorProgressLevel(event),
  };
}

function getRefactorProgressElements(panel) {
  return {
    panel: panel?.querySelector(".refactor-progress-panel"),
    timeline: panel?.querySelector(".refactor-progress-timeline"),
    log: panel?.querySelector(".refactor-progress-log"),
    summary: panel?.querySelector(".refactor-result-summary"),
  };
}

function appendRefactorProgress(panel, event) {
  const { panel: progressPanel, timeline, log } = getRefactorProgressElements(panel);
  if (!progressPanel || !timeline) {
    return;
  }
  progressPanel.classList.remove("hidden");
  const parsed = normalizeRefactorProgressEvent(event);
  const item = document.createElement("li");
  item.className = `refactor-progress-item refactor-progress-${parsed.level}`;
  item.dataset.phase = parsed.phase;
  const time = new Date().toLocaleTimeString();
  item.innerHTML =
    `<span class="refactor-progress-time">${escapeHtml(time)}</span>` +
    `<span class="refactor-progress-phase">${escapeHtml(parsed.phaseLabel)}</span>` +
    `<span class="refactor-progress-message">${escapeHtml(parsed.message)}</span>`;
  timeline.appendChild(item);
  timeline.scrollTop = timeline.scrollHeight;
  if (log) {
    log.textContent += `${parsed.message}\n`;
    log.scrollTop = log.scrollHeight;
  }
}

function clearRefactorProgress(panel) {
  const { panel: progressPanel, timeline, log, summary } = getRefactorProgressElements(panel);
  if (!progressPanel || !timeline) {
    return;
  }
  timeline.innerHTML = "";
  if (log) {
    log.textContent = "";
  }
  progressPanel.classList.remove("hidden");
  summary?.classList.add("hidden");
  if (summary) {
    summary.textContent = "";
  }
}

function renderRefactorResultSummary(panel, result) {
  const { summary } = getRefactorProgressElements(panel);
  if (!summary || !result) {
    return;
  }
  const lines = [];
  lines.push(`Refactor ${result.ok === false ? "FAILED" : "OK"} — ${result.timing?.total_elapsed_ms || 0} ms`);
  if (result.parent?.name || result.parent_copy_name) {
    lines.push(`Parent copy: ${result.parent?.name || result.parent_copy_name}`);
  }
  const compares = result.compares || result.compare_results;
  if (Array.isArray(compares) && compares.length) {
    const equal = compares.filter((row) => row.equal === true).length;
    lines.push(`Compare: ${equal}/${compares.length} equal`);
  }
  if (result.job_cache_key) {
    lines.push(`Cache: ${result.job_cache_key}`);
  }
  summary.textContent = lines.join("\n");
  summary.classList.remove("hidden");
}

async function loadRefactorPresetsIntoPanel(panel) {
  const singleSelect = panel?.querySelector(".refactor-preset-select");
  if (!singleSelect || panel?.dataset.presetsLoaded === "1") {
    return;
  }
  try {
    const payload = await api("/api/playbooks/refactor/presets");
    (payload.presets || []).forEach((preset) => {
      if (preset.steps) {
        return;
      }
      const option = document.createElement("option");
      option.value = preset.id;
      option.textContent = preset.label || preset.id;
      singleSelect.appendChild(option);
    });
    panel.dataset.presetsLoaded = "1";
  } catch (err) {
    console.warn("Could not load refactor configurations", err);
  }
}

function applyRefactorPresetToPanel(panel, preset, analysisData = null) {
  const list = panel.querySelector(".refactor-ops-list");
  const data = analysisData || resolveAnalysisDataForPanel(panel);
  if (list) list.innerHTML = "";
  (preset.leaf_tasks || []).forEach((value) => addRefactorOperation(panel, "leaf", value, data));
  (preset.clusters || []).forEach((value) => addRefactorOperation(panel, "cluster", value, data));
  (preset.post_task_updates || []).forEach((value) => addRefactorOperation(panel, "error", value, data));
}

async function submitRefactorJob(panel, action, payload, runBtnSelector) {
  const resultEl = panel?.querySelector(".refactor-result");
  const runBtn = panel?.querySelector(runBtnSelector);
  clearRefactorProgress(panel);
  if (runBtn) {
    runBtn.disabled = true;
  }

  const finishUi = (result, err) => {
    if (runBtn) {
      runBtn.disabled = false;
    }
    if (err) {
      appendRefactorProgress(panel, { phase: "failed", message: err.message, ok: false });
      if (typeof showOutcomeDialog === "function") {
        showOutcomeDialog({ title: "Refactor failed", message: err.message, success: false });
      } else {
        alert(`Refactor failed: ${err.message}`);
      }
      return;
    }
    if (resultEl) {
      resultEl.textContent = JSON.stringify(result, null, 2);
      resultEl.classList.remove("hidden");
    }
    renderRefactorResultSummary(panel, result);
    const ok = result.ok !== false;
    appendRefactorProgress(panel, {
      phase: ok ? "complete" : "failed",
      message: ok ? "Run complete." : "Run finished with issues.",
      ok,
    });
    if (typeof showOutcomeDialog === "function") {
      const summaryEl = panel?.querySelector(".refactor-result-summary");
      showOutcomeDialog({
        title: ok ? "Refactor complete" : "Refactor finished with issues",
        message: summaryEl?.textContent || (ok ? "See summary below." : "See result JSON for details."),
        success: ok,
      });
    } else if (!ok) {
      alert("Refactor finished with issues — see result JSON.");
    }
  };

  try {
    let result;
    if (window.cptkWs?.isConnected?.()) {
      appendRefactorProgress(panel, "WebSocket job started…");
      result = await window.cptkWs.submitJob(action, payload, {
        timeoutMs: 3600000,
        onStarted: () => appendRefactorProgress(panel, "Job acknowledged by server."),
        onProgress: (event) => appendRefactorProgress(panel, event),
      });
    } else {
      appendRefactorProgress(panel, "WebSocket unavailable — using HTTP POST.");
      result = await withLoader(
        () =>
          api("/api/playbooks/refactor/execute", {
            method: "POST",
            body: JSON.stringify(payload),
          }),
        "Running refactor…",
      );
    }
    finishUi(result);
  } catch (err) {
    finishUi(null, err);
  }
}

async function runRefactorForPanel(details, data) {
  const panel = details.querySelector(".refactor-panel");
  if (!ensureRefactorPanelValid(panel)) {
    return;
  }
  const payload = refactorPayloadFromPanel(details, data);
  if (!payload.leaf_tasks.length && !payload.clusters.length) {
    alert("Add at least one leaf or cluster extract operation.");
    return;
  }
  const summary = [
    "Run refactor on live tenant?",
    "",
    `Playbook: ${data.root_playbook.name}`,
    `Profile: ${data.profile}`,
    `Leaf tasks: ${payload.leaf_tasks.join(", ") || "(none)"}`,
    `Clusters: ${payload.clusters.join(", ") || "(none)"}`,
    `Post updates: ${payload.post_task_updates.join("; ") || "(none)"}`,
    "",
    "Progress streams over WebSocket when connected (falls back to HTTP).",
    "This uploads new sub-playbooks and a parent copy (never overwrites the source playbook).",
  ].join("\n");
  const proceed =
    typeof showConfirmDialog === "function"
      ? await showConfirmDialog({ title: "Confirm refactor", message: summary, proceedLabel: "Run refactor" })
      : window.confirm(summary);
  if (!proceed) {
    return;
  }
  await submitRefactorJob(panel, "playbooks.refactor.execute", payload, ".refactor-run-btn");
}

function bindRefactorPanel(details, data) {
  const panel = details.querySelector(".refactor-panel");
  if (!panel) return;
  loadRefactorPresetsIntoPanel(panel);
  panel.querySelector(".refactor-add-btn")?.addEventListener("click", () => {
    const type = panel.querySelector(".refactor-add-type")?.value || "leaf";
    addRefactorOperation(panel, type, "", data);
  });
  panel.querySelector(".refactor-load-preset-btn")?.addEventListener("click", async () => {
    const presetId = panel.querySelector(".refactor-preset-select")?.value || "";
    if (!presetId) {
      alert("Select a saved configuration to load.");
      return;
    }
    try {
      const preset = await api(`/api/playbooks/refactor/presets/${encodeURIComponent(presetId)}`);
      applyRefactorPresetToPanel(panel, preset, data);
    } catch (err) {
      alert(`Could not load configuration: ${err.message}`);
    }
  });
  panel.querySelector(".refactor-preview-btn")?.addEventListener("click", () => {
    previewRefactorForPanel(details, data);
  });
  panel.querySelector(".refactor-run-btn")?.addEventListener("click", () => {
    runRefactorForPanel(details, data);
  });
}

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function looksLikeUuid(value) {
  return UUID_PATTERN.test(String(value || "").trim());
}

function collectBindingHintsFromAnalysis(data) {
  const hints = [];
  const seen = new Set();
  for (const entry of data.flow_graphs || []) {
    for (const node of entry.graph?.nodes || []) {
      const playbookId = node.playbook_id;
      const playbookName = node.playbook_name;
      if (playbookId && looksLikeUuid(playbookId) && !playbookName) {
        const key = `pb:${entry.playbook_name}:${node.id}:${playbookId}`;
        if (!seen.has(key)) {
          seen.add(key);
          hints.push({
            kind: "playbook",
            playbook: entry.playbook_name,
            taskId: node.id,
            taskLabel: node.label,
            binding: playbookId,
          });
        }
      }
      const scriptId = node.script_id;
      const scriptName = node.script_name;
      const scriptBinding = node.script_binding;
      const bindingLooksUuid = looksLikeUuid(scriptBinding);
      if (scriptId && looksLikeUuid(scriptId) && !scriptName) {
        const key = `sc:${entry.playbook_name}:${node.id}:${scriptId}`;
        if (!seen.has(key)) {
          seen.add(key);
          hints.push({
            kind: "script",
            playbook: entry.playbook_name,
            taskId: node.id,
            taskLabel: node.label,
            binding: scriptBinding || scriptId,
          });
        }
      } else if (bindingLooksUuid && !scriptName) {
        const key = `scb:${entry.playbook_name}:${node.id}:${scriptBinding}`;
        if (!seen.has(key)) {
          seen.add(key);
          hints.push({
            kind: "script",
            playbook: entry.playbook_name,
            taskId: node.id,
            taskLabel: node.label,
            binding: scriptBinding,
          });
        }
      }
    }
  }
  return hints;
}

function renderCopyBindingPreview(host, plan, hints) {
  if (!host) {
    return;
  }
  const lines = [];
  if (hints.length) {
    lines.push("UUID-only bindings in flow graph (enriched from source cache before target upload):");
    hints.forEach((hint) => {
      const where = `${hint.playbook} #${hint.taskId} ${hint.taskLabel}`;
      lines.push(`  · ${hint.kind}: ${where} → ${hint.binding}`);
    });
    lines.push("");
  } else {
    lines.push("No UUID-only playbook/script bindings detected in the flow graph.");
    lines.push("");
  }
  lines.push(`Target: ${plan.target_profile}`);
  lines.push(
    `Playbooks — copy ${plan.playbooks?.counts?.copy || 0}, update ${plan.playbooks?.counts?.update || 0}, skip ${plan.playbooks?.counts?.skip || 0}`,
  );
  lines.push(
    `Scripts — copy ${plan.scripts?.counts?.copy || 0}, update ${plan.scripts?.counts?.update || 0}, skip ${plan.scripts?.counts?.skip || 0}`,
  );
  if (plan.warnings?.length) {
    lines.push("", "Warnings:");
    plan.warnings.forEach((warning) => lines.push(`  - ${warning}`));
  }
  if (plan.missing_sub_playbooks?.length) {
    lines.push("", "Missing sub-playbooks:");
    plan.missing_sub_playbooks.forEach((item) => lines.push(`  - ${item.lookup_key}`));
  }
  host.textContent = lines.join("\n");
  host.classList.remove("hidden");
}

function renderCopyResultSummary(host, copyResult) {
  if (!host || !copyResult) {
    return;
  }
  const lines = [];
  if (copyResult.aborted) {
    lines.push(`Copy aborted: ${copyResult.reason || "no components copied"}`);
    host.textContent = lines.join("\n");
    host.classList.remove("hidden");
    return;
  }
  const scriptResults = copyResult.script_results || [];
  const playbookResults = copyResult.playbook_results || [];
  const scriptsOk = scriptResults.filter((row) => row.status === "copied" || row.status === "updated").length;
  const playbooksOk = playbookResults.filter((row) => row.status === "copied" || row.status === "updated").length;
  lines.push(`Scripts saved: ${scriptsOk}/${scriptResults.length}`);
  lines.push(`Playbooks saved: ${playbooksOk}/${playbookResults.length}`);
  const remapPb = Object.entries(copyResult.playbook_id_remap || {});
  if (remapPb.length) {
    lines.push("", "Playbook ID remap (source → target):");
    remapPb.forEach(([sourceId, targetId]) => lines.push(`  · ${sourceId} → ${targetId}`));
  }
  const remapSc = Object.entries(copyResult.script_id_remap || {});
  if (remapSc.length) {
    lines.push("", "Script ID remap (source → target):");
    remapSc.forEach(([sourceId, targetId]) => lines.push(`  · ${sourceId} → ${targetId}`));
  }
  const unresolved = [];
  playbookResults.forEach((row) => {
    (row.binding_unresolved || []).forEach((issue) => {
      unresolved.push({ playbook: row.name, ...issue });
    });
  });
  (copyResult.binding_issues || []).forEach((issue) => unresolved.push(issue));
  if (unresolved.length) {
    lines.push("", `Unresolved bindings (${unresolved.length}):`);
    unresolved.slice(0, 12).forEach((issue) => {
      const task = issue.task_id ? ` task ${issue.task_id}` : "";
      lines.push(`  · ${issue.playbook_name || issue.playbook || "?"}${task}: ${issue.error || issue.binding || "unresolved"}`);
    });
    if (unresolved.length > 12) {
      lines.push(`  … and ${unresolved.length - 12} more`);
    }
  } else {
    lines.push("", "Bindings: all playbook/script references resolved on upload.");
  }
  host.textContent = lines.join("\n");
  host.classList.remove("hidden");
}

async function previewCopyPlanForPanel(details, data) {
  const target = details.querySelector(".analysis-components-target")?.value;
  if (!target) {
    alert("Choose a target profile.");
    return;
  }
  const payload = {
    source_profile: data.profile,
    target_profile: target,
    playbook_id: data.root_playbook.id,
    overwrite: details.querySelector(".analysis-components-overwrite")?.checked ?? false,
    stop_on_conflict: details.querySelector(".analysis-components-stop")?.checked ?? false,
  };
  const previewHost = details.querySelector(".analysis-copy-binding-preview");
  try {
    const plan = await withLoader(
      () =>
        api("/api/playbooks/copy-components/preview", {
          method: "POST",
          body: JSON.stringify(payload),
        }),
      "Planning component copy…",
    );
    const hints = collectBindingHintsFromAnalysis(data);
    renderCopyBindingPreview(previewHost, plan, hints);
  } catch (err) {
    if (previewHost) {
      previewHost.textContent = `Preview failed: ${err.message}`;
      previewHost.classList.remove("hidden");
    } else {
      alert(`Preview failed: ${err.message}`);
    }
  }
}

window.initPlaybooksAnalysisPanel = initPlaybooksAnalysisPanel;
