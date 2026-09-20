/** WebSocket client: server push notifications + background job requests. */

(function initCptkWebSocket() {
  const RECONNECT_MS = 3000;
  let socket = null;
  let reconnectTimer = null;
  let jobCounter = 0;
  const pendingJobs = new Map();
  const progressHandlers = new Map();

  function wsUrl() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/ws`;
  }

  function ensureToastContainer() {
    let container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.className = "toast-container";
      container.setAttribute("aria-live", "polite");
      document.body.appendChild(container);
    }
    return container;
  }

  function dismissToast(toastEl) {
    if (!toastEl || toastEl.classList.contains("toast-dismissed")) {
      return;
    }
    toastEl.classList.add("toast-dismissed");
    window.setTimeout(() => toastEl.remove(), 220);
  }

  function showToast({ level = "info", title = "", message = "", autoDismissMs = 5000 }) {
    const container = ensureToastContainer();
    const toast = document.createElement("div");
    toast.className = `toast toast-${level}`;
    toast.innerHTML = `
      <div class="toast-body">
        ${title ? `<strong class="toast-title">${escapeHtml(title)}</strong>` : ""}
        <span class="toast-message">${escapeHtml(message)}</span>
      </div>
      <button type="button" class="toast-close" aria-label="Dismiss">×</button>
    `;
    toast.querySelector(".toast-close")?.addEventListener("click", () => dismissToast(toast));
    container.prepend(toast);
    if (autoDismissMs > 0) {
      window.setTimeout(() => dismissToast(toast), autoDismissMs);
    }
    return toast;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function handleMessage(raw) {
    let message;
    try {
      message = JSON.parse(raw);
    } catch {
      return;
    }
    const type = String(message.type || "");

    if (type === "notification") {
      showToast({
        level: message.level || "info",
        title: message.title || "",
        message: message.message || "",
        autoDismissMs: message.autoDismissMs ?? 5000,
      });
      return;
    }

    if (type === "job.started") {
      const jobId = String(message.job_id || "");
      const handler = progressHandlers.get(jobId);
      if (handler?.onStarted) {
        handler.onStarted(message);
      }
      return;
    }

    if (type === "job.progress") {
      const jobId = String(message.job_id || "");
      const handler = progressHandlers.get(jobId);
      if (handler?.onProgress) {
        handler.onProgress(message);
      }
      return;
    }

    if (type === "job.completed" || type === "job.failed") {
      const jobId = String(message.job_id || "");
      const pending = pendingJobs.get(jobId);
      const handler = progressHandlers.get(jobId);
      if (handler) {
        progressHandlers.delete(jobId);
      }
      if (pending) {
        pendingJobs.delete(jobId);
        if (type === "job.completed") {
          pending.resolve(message.result);
        } else {
          pending.reject(new Error(message.error || "Background job failed"));
        }
      }
      return;
    }

    if (type === "log" && message.level === "error") {
      showToast({
        level: "error",
        message: message.message || "Server error",
        autoDismissMs: 8000,
      });
    }
  }

  function connect() {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return;
    }
    socket = new WebSocket(wsUrl());
    socket.addEventListener("open", () => {
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    });
    socket.addEventListener("message", (event) => handleMessage(event.data));
    socket.addEventListener("close", () => {
      socket = null;
      if (!reconnectTimer) {
        reconnectTimer = window.setTimeout(connect, RECONNECT_MS);
      }
    });
    socket.addEventListener("error", () => {
      socket?.close();
    });
  }

  function isConnected() {
    return Boolean(socket && socket.readyState === WebSocket.OPEN);
  }

  function submitJob(action, payload = {}, options = {}) {
    return new Promise((resolve, reject) => {
      if (!isConnected()) {
        reject(new Error("WebSocket not connected"));
        return;
      }
      const jobId = `job-${Date.now()}-${jobCounter += 1}`;
      pendingJobs.set(jobId, { resolve, reject });
      if (options.onProgress || options.onStarted) {
        progressHandlers.set(jobId, {
          onProgress: options.onProgress,
          onStarted: options.onStarted,
        });
      }
      socket.send(JSON.stringify({
        type: "job",
        job_id: jobId,
        action,
        payload,
      }));
      const timeoutMs = Number(options.timeoutMs) || 600000;
      window.setTimeout(() => {
        if (!pendingJobs.has(jobId)) {
          return;
        }
        pendingJobs.delete(jobId);
        progressHandlers.delete(jobId);
        reject(new Error(`Background job timed out: ${action}`));
      }, timeoutMs);
    });
  }

  window.cptkWs = {
    connect,
    isConnected,
    submitJob,
    showToast,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", connect);
  } else {
    connect();
  }
})();
