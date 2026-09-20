/** Shared configuration / script viewer dialog. */

let contentViewerInitialized = false;
let contentViewerActiveTabId = null;

function initContentViewer() {
  if (contentViewerInitialized) return;
  contentViewerInitialized = true;

  const dialog = document.getElementById("content-viewer-dialog");
  const tabsHost = document.getElementById("content-viewer-tabs");
  const copyBtn = document.getElementById("content-viewer-copy");

  tabsHost?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-tab-id]");
    if (!button) return;
    activateContentViewerTab(button.dataset.tabId);
  });

  copyBtn?.addEventListener("click", async () => {
    const panel = document.getElementById("content-viewer-panel");
    if (!panel?.textContent) return;
    try {
      await navigator.clipboard.writeText(panel.textContent);
      window.cptkWs?.showToast?.({
        level: "success",
        message: "Copied to clipboard",
        autoDismissMs: 2500,
      });
    } catch (err) {
      alert(`Copy failed: ${err.message}`);
    }
  });

  dialog?.addEventListener("close", () => {
    contentViewerActiveTabId = null;
  });
}

function activateContentViewerTab(tabId) {
  const tabsHost = document.getElementById("content-viewer-tabs");
  const panel = document.getElementById("content-viewer-panel");
  const tabButtons = tabsHost?.querySelectorAll("[data-tab-id]") || [];
  let activeTab = null;

  tabButtons.forEach((button) => {
    const isActive = button.dataset.tabId === tabId;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
    if (isActive) {
      activeTab = button._tabData;
    }
  });

  if (!panel || !activeTab) return;
  contentViewerActiveTabId = tabId;
  panel.textContent = activeTab.content || activeTab.emptyMessage || "(empty)";
  panel.dataset.format = activeTab.format || "text";
}

function showContentViewer({ title, subtitle = "", tabs = [] }) {
  initContentViewer();
  const dialog = document.getElementById("content-viewer-dialog");
  const titleEl = document.getElementById("content-viewer-title");
  const subtitleEl = document.getElementById("content-viewer-subtitle");
  const tabsHost = document.getElementById("content-viewer-tabs");
  const panel = document.getElementById("content-viewer-panel");
  const visibleTabs = tabs.filter((tab) => tab && (tab.content || tab.emptyMessage));

  if (!dialog || !titleEl || !subtitleEl || !tabsHost || !panel) {
    throw new Error("Content viewer dialog is not available");
  }
  if (!visibleTabs.length) {
    alert("Nothing to display.");
    return;
  }

  titleEl.textContent = title || "Viewer";
  subtitleEl.textContent = subtitle || "";
  subtitleEl.classList.toggle("hidden", !subtitle);

  tabsHost.innerHTML = "";
  visibleTabs.forEach((tab, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "content-viewer-tab";
    button.dataset.tabId = tab.id || `tab-${index}`;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", "false");
    button.textContent = tab.label || tab.id || `Tab ${index + 1}`;
    button._tabData = tab;
    tabsHost.appendChild(button);
  });

  activateContentViewerTab(visibleTabs[0].id || "tab-0");
  dialog.showModal();
}

function contentDetailTabsFromPayload(data) {
  const tabs = [];
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

async function openContentDetailViewer({ title, subtitle = "", fetchUrl, loaderMessage = "Loading…" }) {
  const data = await withLoader(() => api(fetchUrl), loaderMessage);
  const tabs = contentDetailTabsFromPayload(data);
  const resolvedSubtitle =
    subtitle ||
    [data.profile, data.id].filter(Boolean).join(" · ");
  showContentViewer({
    title: title || data.name || data.id || "Viewer",
    subtitle: resolvedSubtitle,
    tabs,
  });
}
