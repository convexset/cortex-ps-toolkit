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
    if (event?.phase === "fetch_script") {
      const name = event.script_name || event.script_id || "script";
      const progress =
        event.current != null && event.total != null ? ` (${event.current}/${event.total})` : "";
      if (event.status === "complete") {
        return `Cached script ${name}${progress}`;
      }
      return `Fetching script ${name} from tenant${progress}…`;
    }
    if (event?.phase === "prefetch_bodies" && event.status === "running") {
      return "Downloading missing playbook and script bodies…";
    }
    if (event?.phase === "fetch_playbook") {
      const name = event.playbook_name || event.playbook_id || "playbook";
      const progress =
        event.current != null && event.total != null ? ` (${event.current}/${event.total})` : "";
      const reasonHint =
        event.reason === "missing_file"
          ? " (first download)"
          : event.reason === "modified_mismatch"
            ? " (re-sync)"
            : "";
      if (event.status === "complete") {
        return `Cached ${name}${progress}${reasonHint}`;
      }
      return `Fetching ${name} from tenant${progress}${reasonHint}…`;
    }
    if (event?.phase === "stage_complete" && event.stage != null && event.stage_total != null) {
      const elapsed =
        event.elapsed_seconds != null ? formatElapsedSeconds(event.elapsed_seconds) : "";
      const label = event.stage_label || event.step || "Step";
      return `Completed Stage ${event.stage}/${event.stage_total} ${label}${elapsed ? ` (Time Elapsed: ${elapsed})` : ""}`;
    }
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
    const elapsed = event?.elapsed_seconds != null ? formatElapsedSeconds(event.elapsed_seconds) : "";
    return elapsed ? `[${elapsed}] ${body}` : body;
  }

  function formatElapsedSeconds(seconds) {
    const total = Math.max(0, Math.round(Number(seconds) || 0));
    const minutes = Math.floor(total / 60);
    const secs = total % 60;
    return minutes ? `${minutes}m ${secs}s` : `${secs}s`;
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
    if (
      event?.phase === "heartbeat" ||
      event?.phase === "step" ||
      event?.phase === "started" ||
      event?.phase === "stage_complete" ||
      event?.phase === "fetch_playbook"
    ) {
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
