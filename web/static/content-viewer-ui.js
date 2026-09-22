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
    const activeTab = getActiveContentViewerTab();
    const text =
      activeTab?.copyText ||
      activeTab?.content ||
      panel?.dataset.copyText ||
      panel?.textContent ||
      "";
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
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

function getActiveContentViewerTab() {
  const tabsHost = document.getElementById("content-viewer-tabs");
  const button = tabsHost?.querySelector(`[data-tab-id="${contentViewerActiveTabId}"]`);
  return button?._tabData || null;
}

function renderContentViewerPanel(panel, tab) {
  if (!panel || !tab) return;
  panel.dataset.format = tab.format || "text";
  panel.dataset.copyText = tab.copyText || tab.content || tab.emptyMessage || "";

  if (tab.format === "html") {
    panel.classList.add("content-viewer-panel--rich");
    panel.classList.remove("content-viewer-panel--text");
    const emptyHtml =
      typeof window.escapeHtml === "function"
        ? window.escapeHtml(tab.emptyMessage || "(empty)")
        : tab.emptyMessage || "(empty)";
    panel.innerHTML = tab.html || `<p class="cvr-empty">${emptyHtml}</p>`;
    return;
  }

  panel.classList.add("content-viewer-panel--text");
  panel.classList.remove("content-viewer-panel--rich");
  panel.innerHTML = "";
  const pre = document.createElement("pre");
  pre.className = "content-viewer-pre";
  pre.textContent = tab.content || tab.emptyMessage || "(empty)";
  panel.appendChild(pre);
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
  renderContentViewerPanel(panel, activeTab);
}

function showContentViewer({ title, subtitle = "", tabs = [] }) {
  initContentViewer();
  const dialog = document.getElementById("content-viewer-dialog");
  const titleEl = document.getElementById("content-viewer-title");
  const subtitleEl = document.getElementById("content-viewer-subtitle");
  const tabsHost = document.getElementById("content-viewer-tabs");
  const panel = document.getElementById("content-viewer-panel");
  const visibleTabs = tabs.filter(
    (tab) =>
      tab &&
      (tab.content ||
        tab.html ||
        tab.emptyMessage ||
        tab.format === "html"),
  );

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

window.showContentViewer = showContentViewer;

async function openContentDetailViewer({ title, subtitle = "", fetchUrl, loaderMessage = "Loading…" }) {
  const data = await withLoader(() => api(fetchUrl), loaderMessage);
  const tabsFn = window.contentDetailTabsFromPayload;
  const tabs = typeof tabsFn === "function" ? tabsFn(data) : [];
  const resolvedSubtitle =
    subtitle ||
    [data.profile, data.id].filter(Boolean).join(" · ");
  showContentViewer({
    title: title || data.name || data.id || "Viewer",
    subtitle: resolvedSubtitle,
    tabs,
  });
}
