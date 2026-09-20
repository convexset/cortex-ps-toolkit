/** Global toolkit settings (cache TTL). */

async function loadSettingsUi() {
  const minutesInput = document.getElementById("settings-cache-ttl-minutes");
  const meta = document.getElementById("settings-meta");
  if (!minutesInput) return;
  try {
    const settings = await api("/api/settings");
    const ttl = Number(settings.cache_ttl_seconds) || 300;
    minutesInput.value = String(Math.max(1, Math.round(ttl / 60)));
    if (meta) {
      meta.textContent = `Cache TTL: ${Math.round(ttl / 60)} minutes`;
    }
  } catch (err) {
    if (meta) meta.textContent = `Settings error: ${err.message}`;
  }
}

async function saveSettingsUi() {
  const minutesInput = document.getElementById("settings-cache-ttl-minutes");
  const meta = document.getElementById("settings-meta");
  if (!minutesInput) return;
  const minutes = Number(minutesInput.value) || 5;
  try {
    const saved = await withLoader(
      () =>
        api("/api/settings", {
          method: "PATCH",
          body: JSON.stringify({ cache_ttl_seconds: Math.max(1, minutes) * 60 }),
        }),
      "Saving settings…",
    );
    if (meta) {
      meta.textContent = `Saved — cache TTL ${Math.round(saved.cache_ttl_seconds / 60)} minutes`;
    }
    if (typeof refreshProfileCacheContext === "function") {
      refreshProfileCacheContext();
    }
  } catch (err) {
    alert(`Save failed: ${err.message}`);
  }
}

function initSettingsUi() {
  document.getElementById("settings-save")?.addEventListener("click", saveSettingsUi);
  loadSettingsUi();
}

window.initSettingsUi = initSettingsUi;
window.loadSettingsUi = loadSettingsUi;
