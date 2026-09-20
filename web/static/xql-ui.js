/** XQL Query Tool — embeds full monitor UI; credentials from toolkit profile picker. */

const XQL_SUPPORTED = new Set(["xsiam", "xdr3", "xdr5", "agentix"]);
const XQL_UNSUPPORTED_HINT =
  "XQL is not available on XSOAR 6 or XSOAR 8. Use an XSIAM, XDR, or AgentiX profile.";

function xqlProfileSupported(slug) {
  const profile = (window.cptkProfiles || []).find((item) => item.slug === slug);
  return profile && XQL_SUPPORTED.has(profile.tenant_type);
}

function initXqlPanel() {
  // Full monitor UI lives in iframe; profile changes reload it.
}

function updateXqlProfileHint() {
  const profile = document.getElementById("active-profile")?.value;
  const hint = document.getElementById("xql-profile-hint");
  if (!hint) return;
  if (!profile) {
    hint.textContent = "Select a profile in the header.";
    hint.classList.add("warn");
    return;
  }
  if (!xqlProfileSupported(profile)) {
    hint.textContent = XQL_UNSUPPORTED_HINT;
    hint.classList.add("warn");
    return;
  }
  hint.textContent = "Uses the active credential profile from API Profiles.";
  hint.classList.remove("warn");
}

function loadXqlForActiveProfile() {
  updateXqlProfileHint();
  const profile = document.getElementById("active-profile")?.value;
  const iframe = document.getElementById("xql-frame");
  if (!iframe) return;
  if (!profile || !xqlProfileSupported(profile)) {
    iframe.removeAttribute("src");
    return;
  }
  const next = `/static/xql-monitor.html?profile=${encodeURIComponent(profile)}`;
  if (iframe.getAttribute("src") !== next) {
    iframe.src = next;
  }
}

window.initXqlPanel = initXqlPanel;
window.loadXqlForActiveProfile = loadXqlForActiveProfile;
window.updateXqlProfileHint = updateXqlProfileHint;
