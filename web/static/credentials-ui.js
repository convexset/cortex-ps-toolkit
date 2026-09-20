/* API Profiles UI */

let credentialsTable = null;
let credentialsGridSearch = null;
let editingSlug = null;

function credActionFormatter(cell) {
  const slug = cell.getRow().getData().slug;
  return `
    <button type="button" class="link-btn" data-action="edit" data-slug="${slug}">Edit</button>
    <button type="button" class="link-btn" data-action="validate" data-slug="${slug}">Validate</button>
    <button type="button" class="link-btn danger" data-action="delete" data-slug="${slug}">Delete</button>
  `;
}

function initCredentialsGrid() {
  credentialsTable = new Tabulator("#credentials-grid", {
    height: "460px",
    layout: "fitColumns",
    placeholder: "No profiles — Import lab or Add profile",
    columns: [
      { title: "Slug", field: "slug", width: 160 },
      { title: "Platform", field: "tenant_type", width: 90 },
      { title: "API ID", field: "api_id", width: 70 },
      { title: "URL", field: "url", minWidth: 220 },
      { title: "Key", field: "key_masked", width: 80 },
      {
        title: "TLS",
        field: "verify_ssl",
        width: 60,
        formatter: (cell) => (cell.getValue() === false ? "skip" : "verify"),
      },
      { title: "Expires", field: "expires_at", width: 120, formatter: (c) => c.getValue() || "—" },
      { title: "Actions", formatter: credActionFormatter, width: 200, headerSort: false },
    ],
  });

  const searchInput = document.getElementById("credentials-search");
  if (searchInput) {
    credentialsGridSearch = attachGridSearch(credentialsTable, searchInput, {
      selectable: false,
      idField: "slug",
      nameField: "label",
    });
  }

  document.getElementById("credentials-grid").addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-action]");
    if (!btn) return;
    const slug = btn.dataset.slug;
    const action = btn.dataset.action;
    if (action === "edit") openCredDialog(slug);
    if (action === "validate") await validateCredential(slug);
    if (action === "delete") await deleteCredential(slug);
  });
}

function openCredDialog(slug) {
  const dialog = document.getElementById("cred-dialog");
  const form = document.getElementById("cred-form");
  form.reset();
  editingSlug = slug || null;
  document.getElementById("cred-dialog-title").textContent = slug ? `Edit ${slug}` : "Add profile";
  const keyInput = form.elements.key;
  keyInput.required = !slug;
  keyInput.placeholder = slug ? "Leave blank to keep existing key" : "Required";

  if (slug) {
    const profile = profiles.find((p) => p.slug === slug);
    if (profile) {
      form.elements.label.value = profile.label;
      form.elements.slug.value = profile.slug;
      form.elements.url.value = profile.url;
      form.elements.api_id.value = profile.api_id || "";
      form.elements.tenant_type.value = profile.tenant_type || "";
      form.elements.expires_at.value = profile.expires_at || "";
      form.elements.verify_ssl.checked = profile.verify_ssl !== false;
      form.elements.notes.value = profile.notes || "";
    }
  }
  dialog.showModal();
}

async function saveCredentialForm(event) {
  event.preventDefault();
  const form = event.target;
  const payload = {
    label: form.elements.label.value.trim(),
    slug: form.elements.slug.value.trim() || undefined,
    url: form.elements.url.value.trim(),
    api_id: form.elements.api_id.value.trim(),
    key: form.elements.key.value,
    tenant_type: form.elements.tenant_type.value || undefined,
    expires_at: form.elements.expires_at.value.trim() || undefined,
    verify_ssl: form.elements.verify_ssl.checked,
    notes: form.elements.notes.value.trim(),
  };
  if (!payload.key) delete payload.key;

  try {
    await withLoader(async () => {
      if (editingSlug) {
        await api(`/api/credentials/${encodeURIComponent(editingSlug)}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
      } else {
        if (!payload.key) {
          alert("API key is required for new profiles.");
          return;
        }
        await api("/api/credentials", { method: "POST", body: JSON.stringify(payload) });
      }
      document.getElementById("cred-dialog").close();
      await refreshCredentialsView();
    }, "Saving profile…");
  } catch (err) {
    alert(`Save failed: ${err.message}`);
  }
}

async function validateCredential(slug) {
  const resultEl = document.getElementById("cred-action-result");
  resultEl.classList.remove("hidden");
  try {
    const data = await withLoader(
      () => api(`/api/credentials/${encodeURIComponent(slug)}/validate`, { method: "POST", body: "{}" }),
      `Validating ${slug}…`,
    );
    resultEl.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    resultEl.textContent = `Error: ${err.message}`;
  }
}

async function deleteCredential(slug) {
  if (!confirm(`Delete profile ${slug}? Cache will be removed.`)) return;
  try {
    await withLoader(async () => {
      await api(`/api/credentials/${encodeURIComponent(slug)}`, { method: "DELETE" });
      await refreshCredentialsView();
    }, `Deleting ${slug}…`);
  } catch (err) {
    alert(`Delete failed: ${err.message}`);
  }
}

async function importLabCredentials() {
  try {
    await withLoader(async () => {
      const data = await api("/api/credentials/import-lab", { method: "POST", body: "{}" });
      document.getElementById("cred-action-result").textContent = JSON.stringify(data, null, 2);
      document.getElementById("cred-action-result").classList.remove("hidden");
      await refreshCredentialsView();
    }, "Importing lab profiles…");
  } catch (err) {
    alert(`Import failed: ${err.message}`);
  }
}

async function purgeExpiredCredentials() {
  try {
    await withLoader(async () => {
      const data = await api("/api/credentials/purge-expired", {
        method: "POST",
        body: JSON.stringify({ dry_run: false }),
      });
      document.getElementById("cred-action-result").textContent = JSON.stringify(data, null, 2);
      document.getElementById("cred-action-result").classList.remove("hidden");
      await refreshCredentialsView();
    }, "Purging expired profiles…");
  } catch (err) {
    alert(`Purge failed: ${err.message}`);
  }
}

async function refreshCredentialsView() {
  await withLoader(async () => {
    await loadCredentials();
    if (credentialsTable) {
      credentialsTable.setData(profiles);
      if (credentialsGridSearch) {
        credentialsGridSearch.applySearch();
      }
      document.getElementById("cred-meta").textContent = `${profiles.length} profile(s)`;
    }
  }, "Loading profiles…");
}

function bindCredentialsEvents() {
  document.getElementById("cred-add").addEventListener("click", () => openCredDialog(null));
  document.getElementById("cred-import-lab").addEventListener("click", importLabCredentials);
  document.getElementById("cred-purge-expired").addEventListener("click", purgeExpiredCredentials);
  document.getElementById("cred-form").addEventListener("submit", saveCredentialForm);
  document.getElementById("cred-cancel").addEventListener("click", () => {
    document.getElementById("cred-dialog").close();
  });
}

function initCredentialsSection() {
  if (!credentialsTable) {
    initCredentialsGrid();
    bindCredentialsEvents();
  }
  refreshCredentialsView();
}
