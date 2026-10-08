/** Bundles section: collect assets and copy across tenants. */

const cptkBundleBasket = { items: [] };

function bundleItemKey(asset, id) {
  return `${asset}:${id}`;
}

function renderBundleSummary() {
  const summary = document.getElementById("bundles-workflow-summary");
  const listEl = document.getElementById("bundles-workflow-list");
  if (!summary || !listEl) return;
  const n = cptkBundleBasket.items.length;
  summary.textContent = n ? `${n} item(s) in bundle` : "Bundle empty";
  listEl.classList.toggle("hidden", n === 0);
  listEl.replaceChildren();
  for (const item of cptkBundleBasket.items) {
    const li = document.createElement("li");
    li.textContent = `${item.asset} · ${item.name}`;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = "Remove";
    btn.addEventListener("click", () => {
      cptkBundleBasket.items = cptkBundleBasket.items.filter((row) => row.key !== item.key);
      renderBundleSummary();
    });
    li.append(" ", btn);
    listEl.append(li);
  }
}

function cptkAddToBundle(asset, row) {
  const id = String(row.id || row.name || "");
  if (!asset || !id) return false;
  const key = bundleItemKey(asset, id);
  if (cptkBundleBasket.items.some((item) => item.key === key)) return false;
  cptkBundleBasket.items.push({
    key,
    asset,
    id,
    name: row.name || id,
    type: row.type || asset,
  });
  renderBundleSummary();
  return true;
}

window.cptkAddToBundle = cptkAddToBundle;
window.cptkBundleBasket = cptkBundleBasket;

function initBundlesSection() {
  const saveBtn = document.getElementById("bundles-save");
  const loadBtn = document.getElementById("bundles-load");
  const deleteBtn = document.getElementById("bundles-delete");
  const copyBtn = document.getElementById("bundles-copy");
  const clearBtn = document.getElementById("bundles-clear");

  async function refreshSavedBundles() {
    const select = document.getElementById("bundles-preset");
    const source = document.getElementById("active-profile")?.value || "";
    if (!select || !source) return;
    const data = await api(`/api/bundles?profile=${encodeURIComponent(source)}`);
    select.replaceChildren();
    select.append(new Option("— select —", ""));
    for (const bundle of data.bundles || []) {
      select.append(new Option(bundle.name || bundle.id, bundle.id));
    }
  }

  clearBtn?.addEventListener("click", () => {
    cptkBundleBasket.items = [];
    renderBundleSummary();
  });

  saveBtn?.addEventListener("click", async () => {
    const name = document.getElementById("bundles-id")?.value?.trim();
    const source = document.getElementById("active-profile")?.value || "";
    if (!name || !source || !cptkBundleBasket.items.length) {
      alert("Name, source profile, and at least one bundle item required.");
      return;
    }
    await api("/api/bundles", {
      method: "POST",
      body: JSON.stringify({
        name,
        source_profile: source,
        items: cptkBundleBasket.items.map(({ asset, id, name: n, type }) => ({ asset, id, name: n, type })),
      }),
    });
    await refreshSavedBundles();
  });

  loadBtn?.addEventListener("click", async () => {
    const bundleId = document.getElementById("bundles-preset")?.value;
    const source = document.getElementById("active-profile")?.value || "";
    if (!bundleId || !source) return;
    const preset = await api(`/api/bundles/${encodeURIComponent(bundleId)}?profile=${encodeURIComponent(source)}`);
    const resolved = await api("/api/bundles/resolve", {
      method: "POST",
      body: JSON.stringify({ profile: source, items: preset.items || [] }),
    });
    cptkBundleBasket.items = (resolved.items || []).map((item) => ({
      key: bundleItemKey(item.asset, String(item.id)),
      asset: item.asset,
      id: String(item.id),
      name: item.name || String(item.id),
      type: item.type || item.asset,
    }));
    renderBundleSummary();
  });

  deleteBtn?.addEventListener("click", async () => {
    const bundleId = document.getElementById("bundles-preset")?.value;
    const source = document.getElementById("active-profile")?.value || "";
    if (!bundleId || !source) return;
    await api(`/api/bundles/${encodeURIComponent(bundleId)}?profile=${encodeURIComponent(source)}`, {
      method: "DELETE",
    });
    await refreshSavedBundles();
  });

  copyBtn?.addEventListener("click", async () => {
    const source = document.getElementById("active-profile")?.value || "";
    const target = document.getElementById("bundles-copy-target")?.value || "";
    if (!source || !target || !cptkBundleBasket.items.length) {
      alert("Source, target, and bundle items required.");
      return;
    }
    const payload = {
      source_profile: source,
      target_profile: target,
      items: cptkBundleBasket.items.map(({ asset, id, name, type }) => ({ asset, id, name, type })),
      shallow_playbooks: true,
    };
    if (typeof mergeCopyPayload === "function") {
      Object.assign(payload, readCopyModeFromRow("bundles"));
    }
    const plan = await withLoader(
      () => api("/api/bundles/copy/preview", { method: "POST", body: JSON.stringify(payload) }),
      "Planning bundle copy…",
    );
    const proceed =
      typeof confirmOperation === "function"
        ? await confirmOperation({ title: "Confirm bundle copy", plan, proceedLabel: "Copy bundle", itemLabel: "asset" })
        : window.confirm("Copy bundle?");
    if (!proceed) return;
    const result = await withLoader(
      () => api("/api/bundles/copy", { method: "POST", body: JSON.stringify(payload) }),
      "Copying bundle…",
    );
    const out = document.getElementById("bundles-action-result");
    if (out) {
      out.textContent = JSON.stringify(result, null, 2);
      out.classList.remove("hidden");
    }
  });

  return { loadForActiveProfile: async () => refreshSavedBundles() };
}

let bundlesTools = null;
document.addEventListener("DOMContentLoaded", () => {
  bundlesTools = initBundlesSection();
  renderBundleSummary();
  const copyRow = document.getElementById("bundles-copy-row");
  if (copyRow && typeof appendCopyModeControls === "function") {
    appendCopyModeControls(copyRow, "bundles");
  }
});
