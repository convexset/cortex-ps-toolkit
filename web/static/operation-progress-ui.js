/** Toast + WebSocket progress helpers for long-running operations. */

const PROGRESS_TOAST_AUTO_DISMISS_MS = 5000;

function setButtonBusy(button, busy, busyLabel = "Copying…") {
  if (!button) return;
  if (busy) {
    if (!button.dataset.cptkIdleLabel) {
      button.dataset.cptkIdleLabel = button.textContent;
    }
    button.textContent = busyLabel;
    button.disabled = true;
    button.classList.add("is-busy");
    button.setAttribute("aria-busy", "true");
    return;
  }
  if (button.dataset.cptkIdleLabel) {
    button.textContent = button.dataset.cptkIdleLabel;
  }
  button.disabled = false;
  button.classList.remove("is-busy");
  button.removeAttribute("aria-busy");
}

function createOperationProgress(title) {
  let progressToast = null;

  function formatProgressMessage(event) {
    const current = event?.current || {};
    const parts = [];
    if (current.source && current.target) parts.push(`${current.source} → ${current.target}`);
    if (current.asset || current.section) parts.push(current.asset || current.section);
    if (current.item_id) parts.push(String(current.item_id));
    if (current.target_name) parts.push(String(current.target_name));
    if (current.step) parts.push(String(current.step));
    if (current.status) parts.push(String(current.status));
    if (current.item_count != null) parts.push(`${current.item_count} item(s)`);
    const body = parts.join(" · ") || "Working…";
    const elapsed = event?.elapsed_seconds != null ? `${event.elapsed_seconds}s` : "";
    return elapsed ? `[${elapsed}] ${body}` : body;
  }

  function show(message) {
    const text = String(message || "Working…");
    if (window.cptkWs?.showToast) {
      if (progressToast) {
        const msgEl = progressToast.querySelector(".toast-message");
        if (msgEl) msgEl.textContent = text;
        return;
      }
      progressToast = window.cptkWs.showToast({
        level: "info",
        title,
        message: text,
        autoDismissMs: PROGRESS_TOAST_AUTO_DISMISS_MS,
      });
    }
  }

  function clear() {
    if (progressToast) {
      progressToast.querySelector(".toast-close")?.click();
      progressToast = null;
    }
  }

  function onProgress(event) {
    if (event?.phase === "heartbeat" || event?.phase === "step" || event?.phase === "started") {
      show(formatProgressMessage(event));
    }
  }

  function wsJobOptions(options = {}) {
    const startMessage = options.startMessage;
    return {
      timeoutMs: options.timeoutMs ?? 900000,
      onStarted: () => {
        if (startMessage) show(startMessage);
        options.onStarted?.();
      },
      onProgress: (event) => {
        onProgress(event);
        options.onProgress?.(event);
      },
    };
  }

  async function runCopy({
    startMessage,
    wsAction,
    payload,
    httpCall,
    loaderMessage,
    busyButton = null,
    busyLabel = null,
  }) {
    const message = loaderMessage || startMessage || "Copying…";
    show(startMessage || message);
    if (typeof window.showLoader === "function") {
      window.showLoader(message);
    }
    setButtonBusy(busyButton, true, busyLabel || message);
    try {
      if (window.cptkWs?.isConnected?.() && wsAction) {
        return await window.cptkWs.submitJob(
          wsAction,
          payload,
          wsJobOptions({ startMessage: message, timeoutMs: 900000 }),
        );
      }
      if (httpCall) {
        return await httpCall();
      }
      throw new Error("No copy handler configured");
    } finally {
      if (typeof window.hideLoader === "function") {
        window.hideLoader();
      }
      setButtonBusy(busyButton, false);
      clear();
    }
  }

  return {
    show,
    clear,
    onProgress,
    formatProgressMessage,
    wsJobOptions,
    runCopy,
  };
}

window.createOperationProgress = createOperationProgress;
window.setButtonBusy = setButtonBusy;
