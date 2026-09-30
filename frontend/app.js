/* ============================================================
   Wholesale Banking KYC & Policy Verification Dashboard (app.js)
   ============================================================ */
const API = "/api";

const state = {
  rules: [],
  bundles: [],
  filter: "",
  expanded: new Set(),
  running: new Set(),
  runningAll: false,
};

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

function icons() {
  if (window.lucide) window.lucide.createIcons();
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

async function api(path, opts = {}) {
  const res = await fetch(API + path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try {
      msg = (await res.json()).detail || msg;
    } catch {}
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}

function toast(kind, title, msg = "") {
  const t = document.createElement("div");
  t.className = "toast " + kind;
  const ic = kind === "ok" ? "check-circle-2" : kind === "err" ? "alert-circle" : "info";
  t.innerHTML = `<i data-lucide="${ic}"></i><div class="toast-body">
    <strong>${esc(title)}</strong>${msg ? `<span>${esc(msg)}</span>` : ""}</div>`;
  $("#toast-stack").appendChild(t);
  icons();
  setTimeout(() => {
    t.classList.add("out");
    setTimeout(() => t.remove(), 220);
  }, 4000);
}

function openModal(id) { $("#" + id).classList.add("show"); }
function closeModal(id) { $("#" + id).classList.remove("show"); }

$$(".modal-overlay").forEach((ov) => {
  ov.addEventListener("mousedown", (e) => { if (e.target === ov) ov.classList.remove("show"); });
  $$("[data-close]", ov).forEach((b) => b.addEventListener("click", () => ov.classList.remove("show")));
});

let confirmCb = null;
function confirmDialog(title, text, okLabel, cb) {
  $("#confirm-title").textContent = title;
  $("#confirm-text").textContent = text;
  $("#confirm-ok").textContent = okLabel;
  confirmCb = cb;
  openModal("modal-confirm");
}
$("#confirm-ok").addEventListener("click", () => {
  closeModal("modal-confirm");
  if (confirmCb) confirmCb();
});

/* ===================== INITIALIZE ========================= */
async function init() {
  bindGlobal();
  bindAuth();
  try {
    await api("/me");
    await showApp();
  } catch {
    showLogin();
  }
}

function showLogin() {
  $("#login-view").style.display = "flex";
  $("#app-view").style.display = "none";
  $("#login-password").value = "";
  $("#login-error").textContent = "";
  icons();
}

async function showApp() {
  $("#login-view").style.display = "none";
  $("#app-view").style.display = "";
  try {
    state.rules = await api("/rules");
  } catch {}
  await loadDashboard();
  icons();
}

function bindAuth() {
  $("#login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("#login-btn");
    btn.disabled = true;
    const body = new FormData();
    body.append("username", $("#login-username").value);
    body.append("password", $("#login-password").value);
    try {
      await api("/login", { method: "POST", body });
      await showApp();
    } catch (err) {
      $("#login-error").textContent = err.message || "Login failed";
    } finally {
      btn.disabled = false;
    }
  });

  $("#btn-logout").addEventListener("click", async () => {
    try { await api("/logout", { method: "POST" }); } catch {}
    showLogin();
  });
}

function bindGlobal() {
  $("#btn-new-entity").addEventListener("click", () => {
    $("#new-entity-name").value = "";
    $("#new-entity-uen").value = "";
    openModal("modal-new-entity");
  });

  $("#form-new-entity").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = $("#new-entity-name").value.trim();
    const uen = $("#new-entity-uen").value.trim();
    const type = $("#new-entity-type").value;
    if (!name) return;
    const body = new FormData();
    body.append("name", name);
    if (uen) body.append("uen", uen);
    body.append("entity_type", type);
    try {
      const b = await api("/bundles", { method: "POST", body });
      closeModal("modal-new-entity");
      toast("ok", "Client file created", b.name);
      state.expanded.add(b.id);
      await loadDashboard();
    } catch (err) {
      toast("err", "Creation failed", err.message);
    }
  });

  $("#entity-search").addEventListener("input", (e) => {
    state.filter = e.target.value.toLowerCase().trim();
    renderList();
  });

  $("#btn-run-all").addEventListener("click", async () => {
    if (state.runningAll) return;
    state.runningAll = true;
    $("#btn-run-all").disabled = true;
    toast("info", "Batch Verification", "Evaluating all corporate files against policy rules...");
    try {
      await api("/verify-all", { method: "POST" });
      toast("ok", "Batch Completed", "All corporate document bundles verified.");
      await loadDashboard();
    } catch (err) {
      toast("err", "Verification failed", err.message);
    } finally {
      state.runningAll = false;
      $("#btn-run-all").disabled = false;
    }
  });
}

async function loadDashboard() {
  try {
    state.bundles = await api("/bundles");
    renderList();
  } catch (err) {
    if (err.message.includes("401") || err.message.includes("Not authenticated")) {
      showLogin();
    } else {
      toast("err", "Failed to load bundles", err.message);
    }
  }
}

function renderList() {
  const filtered = state.bundles.filter((b) => {
    if (!state.filter) return true;
    const txt = `${b.name} ${b.uen || ""} ${b.entity_type}`.toLowerCase();
    return txt.includes(state.filter);
  });

  $("#entity-count").textContent = state.bundles.length;
  const listEl = $("#customer-list");
  listEl.innerHTML = "";

  if (filtered.length === 0) {
    listEl.innerHTML = `<div style="text-align:center; padding: 48px; background:#fff; border-radius:10px; border:1px solid #e2e8f0;">
      <i data-lucide="building" style="width:42px;height:42px;color:#94a3b8;margin-bottom:8px"></i>
      <p style="font-weight:600; color:#334155;">No corporate client files found</p>
      <p style="font-size:12px; color:#64748b;">Create a new client file or upload document folders.</p>
    </div>`;
    icons();
    return;
  }

  filtered.forEach((bundle) => {
    listEl.appendChild(renderBundleRow(bundle));
  });
  icons();
}

function renderBundleRow(b) {
  const isExp = state.expanded.has(b.id);
  const isRunning = state.running.has(b.id);
  const verdict = b.last_run?.overall_verdict || b.status || "PENDING";
  
  const row = document.createElement("div");
  row.className = `customer-row ${isExp ? "open" : ""}`;
  row.id = `bundle-${b.id}`;

  const verdictBadge = verdict === "PASS"
    ? `<span class="badge badge-pass"><i data-lucide="check-circle-2"></i> PASS</span>`
    : verdict === "FAIL"
    ? `<span class="badge badge-fail"><i data-lucide="x-circle"></i> FAIL</span>`
    : `<span class="badge badge-na"><i data-lucide="clock"></i> PENDING</span>`;

  row.innerHTML = `
    <div class="row-header" data-toggle="${b.id}">
      <div class="row-left">
        <div class="avatar">${esc(b.name.substring(0, 2).toUpperCase())}</div>
        <div class="name-block">
          <span class="customer-name">${esc(b.name)}</span>
          <span class="customer-meta">UEN: <b>${esc(b.uen || "Pending Verification")}</b> &nbsp;·&nbsp; ${esc(b.entity_type)} &nbsp;·&nbsp; <b>${b.doc_count}</b> doc(s)</span>
        </div>
      </div>
      <div class="row-right">
        ${verdictBadge}
        <div class="row-actions" onclick="event.stopPropagation()">
          <button class="btn btn-sm btn-accent btn-verify" data-run="${b.id}" ${isRunning ? "disabled" : ""}>
            <i data-lucide="${isRunning ? 'loader-2' : 'zap'}" class="${isRunning ? 'spin' : ''}"></i>
            ${isRunning ? "Validating..." : "Run Validation"}
          </button>
          <a class="btn btn-sm btn-ghost" href="/api/bundles/${b.id}/report.pdf" target="_blank" title="Download PDF Audit Report">
            <i data-lucide="file-text"></i> Audit PDF
          </a>
          <button class="icon-btn btn-del" data-del="${b.id}" title="Delete client file">
            <i data-lucide="trash-2"></i>
          </button>
        </div>
        <button class="icon-btn toggle-btn"><i data-lucide="${isExp ? 'chevron-up' : 'chevron-down'}"></i></button>
      </div>
    </div>
    ${isExp ? renderBundleDetail(b) : ""}
  `;

  row.querySelector(`[data-toggle="${b.id}"]`).addEventListener("click", () => {
    if (state.expanded.has(b.id)) state.expanded.delete(b.id);
    else state.expanded.add(b.id);
    renderList();
  });

  const verifyBtn = row.querySelector(`[data-run="${b.id}"]`);
  if (verifyBtn) {
    verifyBtn.addEventListener("click", async () => {
      await runVerification(b.id);
    });
  }

  const delBtn = row.querySelector(`[data-del="${b.id}"]`);
  if (delBtn) {
    delBtn.addEventListener("click", () => {
      confirmDialog("Delete Client Bundle", `Are you sure you want to delete ${b.name}?`, "Delete", async () => {
        try {
          await api(`/bundles/${b.id}`, { method: "DELETE" });
          toast("ok", "Bundle deleted", b.name);
          await loadDashboard();
        } catch (err) {
          toast("err", "Failed to delete", err.message);
        }
      });
    });
  }

  if (isExp) {
    bindDetailEvents(row, b);
  }

  return row;
}

function renderBundleDetail(b) {
  const docs = b.documents || [];
  const run = b.last_run || null;

  // Check presence of specific required documents
  const hasBizfile = docs.some(d => d.doc_type === 'bizfile' || d.original_name.toLowerCase().includes('bizfile') || d.original_name.toLowerCase().includes('profile') || d.original_name.toLowerCase().includes('acra'));
  const hasMaa = docs.some(d => d.doc_type === 'maa' || d.original_name.toLowerCase().includes('maa') || d.original_name.toLowerCase().includes('memorandum') || d.original_name.toLowerCase().includes('articles') || d.original_name.toLowerCase().includes('constitution'));
  const hasRom = docs.some(d => d.doc_type === 'rom' || d.original_name.toLowerCase().includes('rom') || d.original_name.toLowerCase().includes('members') || d.original_name.toLowerCase().includes('register') || d.original_name.toLowerCase().includes('shareholder'));
  const hasBoard = docs.some(d => d.doc_type === 'board_resolution' || d.original_name.toLowerCase().includes('board') || d.original_name.toLowerCase().includes('resolution') || d.original_name.toLowerCase().includes('mandate'));

  return `
    <div class="row-detail">
      <div class="detail-grid" style="display:grid; grid-template-columns: 1fr 1.25fr; gap: 20px;">
        
        <!-- Left: Ingestion & Document Requirements Checklist -->
        <div class="card-box">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:14px;">
            <div>
              <h4 style="font-weight:700; font-size:14px; color:var(--navy)"><i data-lucide="folder-check"></i> Ingest Corporate Document Folder</h4>
              <p style="font-size:11.5px; color:var(--muted); margin-top:2px;">Wholesale policy requires the following 4 corporate documents:</p>
            </div>
            <label class="btn btn-sm btn-primary" style="cursor:pointer" title="Upload folder or multiple documents">
              <i data-lucide="upload-cloud"></i> Ingest Folder / Files
              <input type="file" multiple class="doc-upload-input" data-bundle="${b.id}" style="display:none" />
            </label>
          </div>

          <!-- Document Requirement Checkpoints -->
          <div class="req-checklist" style="display:flex; flex-direction:column; gap:8px; margin-bottom:16px; padding:12px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px;">
            
            <div style="display:flex; justify-content:space-between; align-items:center; font-size:12px;">
              <span style="display:flex; align-items:center; gap:6px;">
                <i data-lucide="${hasBizfile ? 'check-circle-2' : 'alert-circle'}" style="color:${hasBizfile ? '#16a34a' : '#ea580c'}; width:14px; height:14px;"></i>
                <b>1. Business Profile / ACRA BizFile</b> (last 12 months)
              </span>
              <span class="badge ${hasBizfile ? 'badge-pass' : 'badge-warn'}" style="font-size:10.5px; padding:2px 7px;">${hasBizfile ? 'Provided' : 'Required'}</span>
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; font-size:12px;">
              <span style="display:flex; align-items:center; gap:6px;">
                <i data-lucide="${hasMaa ? 'check-circle-2' : 'alert-circle'}" style="color:${hasMaa ? '#16a34a' : '#ea580c'}; width:14px; height:14px;"></i>
                <b>2. Memorandum and Articles of Association (M&AA)</b> (CTC)
              </span>
              <span class="badge ${hasMaa ? 'badge-pass' : 'badge-warn'}" style="font-size:10.5px; padding:2px 7px;">${hasMaa ? 'Provided' : 'Required'}</span>
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; font-size:12px;">
              <span style="display:flex; align-items:center; gap:6px;">
                <i data-lucide="${hasRom ? 'check-circle-2' : 'alert-circle'}" style="color:${hasRom ? '#16a34a' : '#ea580c'}; width:14px; height:14px;"></i>
                <b>3. Register of Members (ROM)</b> (CTC)
              </span>
              <span class="badge ${hasRom ? 'badge-pass' : 'badge-warn'}" style="font-size:10.5px; padding:2px 7px;">${hasRom ? 'Provided' : 'Required'}</span>
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; font-size:12px;">
              <span style="display:flex; align-items:center; gap:6px;">
                <i data-lucide="${hasBoard ? 'check-circle-2' : 'info'}" style="color:${hasBoard ? '#16a34a' : '#64748b'}; width:14px; height:14px;"></i>
                <b>4. Board Resolution</b> (Where applicable, CTC)
              </span>
              <span class="badge ${hasBoard ? 'badge-pass' : 'badge-na'}" style="font-size:10.5px; padding:2px 7px;">${hasBoard ? 'Provided' : 'Conditional'}</span>
            </div>

          </div>

          <!-- Uploaded Documents Ingested List -->
          <h5 style="font-size:12px; font-weight:700; color:var(--navy); margin-bottom:8px;">Ingested Files on Record (${docs.length})</h5>
          <div class="doc-list" style="display:flex; flex-direction:column; gap:8px;">
            ${docs.length === 0 ? '<div style="padding:16px; text-align:center; background:#fff; border:1px dashed #cbd5e1; border-radius:6px; color:#64748b; font-size:12px;">Click "Ingest Folder / Files" to upload the 4 required client documents.</div>' : ''}
            ${docs.map(d => `
              <div class="doc-item" style="display:flex; justify-content:space-between; align-items:center; padding:9px 12px; background:#fff; border:1px solid #e2e8f0; border-radius:6px;">
                <div style="display:flex; align-items:center; gap:8px;">
                  <i data-lucide="file-text" style="color:var(--blue)"></i>
                  <div>
                    <div style="font-weight:600; font-size:13px; color:var(--navy);">${esc(d.original_name)}</div>
                    <div style="font-size:11.5px; color:#64748b;">
                      Detected: <b style="color:var(--navy-2)">${esc(d.doc_type)}</b> 
                      ${d.is_ctc ? '· <span style="color:#16a34a; font-weight:700;">Certified True Copy (CTC) ✓</span>' : '· <span style="color:#94a3b8;">Standard Copy</span>'}
                    </div>
                  </div>
                </div>
                <button class="icon-btn btn-del-doc" data-doc="${d.id}" title="Remove file"><i data-lucide="trash-2"></i></button>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- Right: Policy Check Breakdown (Desc 1, 2, 3) -->
        <div class="card-box">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <h4 style="font-weight:700; font-size:14px; color:var(--navy)"><i data-lucide="shield-check"></i> Wholesale Policy Verification & AI Audit</h4>
          </div>

          ${!run ? `
            <div style="padding:24px; text-align:center; background:#f8fafc; border:1px dashed #cbd5e1; border-radius:6px; color:#64748b; font-size:13px;">
              Click <b>Run Validation</b> to test the 4 mandatory documents against wholesale bank policies (BizFile $<12$m, M&AA/ROM CTC status, and Directorship/Ownership).
            </div>
          ` : `
            <div style="padding:10px 14px; border-radius:6px; margin-bottom:12px; background:${run.overall_verdict === 'PASS' ? '#f0fdf4' : '#fef2f2'}; border:1px solid ${run.overall_verdict === 'PASS' ? '#bbf7d0' : '#fecaca'}; font-weight:700; font-size:13px; color:${run.overall_verdict === 'PASS' ? '#16a34a' : '#dc2626'};">
              OVERALL VERDICT: ${run.overall_verdict} — ${esc(run.summary || '')}
            </div>

            <div class="checks-list" style="display:flex; flex-direction:column; gap:10px;">
              ${(run.results || []).map(r => `
                <div style="padding:12px; border-radius:6px; border:1px solid ${r.verdict === 'PASS' ? '#bbf7d0' : '#fecaca'}; background:${r.verdict === 'PASS' ? '#ffffff' : '#fffafb'};">
                  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                    <span style="font-weight:700; color:var(--navy); font-size:13px;">${esc(r.check_id)}: ${esc(r.rule_name)}</span>
                    <span class="badge ${r.verdict === 'PASS' ? 'badge-pass' : 'badge-fail'}">${r.verdict}</span>
                  </div>
                  <div style="font-size:12.5px; color:#334155; line-height:1.4;">${esc(r.evidence)}</div>
                  ${r.reason_code ? `
                    <div style="margin-top:6px; font-size:12px; font-weight:700; color:#dc2626; display:flex; gap:12px;">
                      <span>Reason: <mark style="background:#fee2e2; color:#dc2626; padding:1px 5px; border-radius:4px;">${esc(r.reason_code)}</mark></span>
                      <span>Priority: <mark style="background:#fee2e2; color:#dc2626; padding:1px 5px; border-radius:4px;">${esc(r.priority)}</mark></span>
                    </div>
                  ` : ''}
                </div>
              `).join('')}
            </div>
          `}
        </div>

      </div>
    </div>
  `;
}

function bindDetailEvents(row, bundle) {
  const uploadInput = row.querySelector(`.doc-upload-input[data-bundle="${bundle.id}"]`);
  if (uploadInput) {
    uploadInput.addEventListener("change", async (e) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;
      const body = new FormData();
      for (let i = 0; i < files.length; i++) {
        body.append("files", files[i]);
      }
      try {
        toast("info", "Ingesting Documents", `Uploading ${files.length} document(s)...`);
        await api(`/bundles/${bundle.id}/documents/batch`, { method: "POST", body });
        toast("ok", "Ingestion Complete", `${files.length} document(s) added to client record.`);
        const fullBundle = await api(`/bundles/${bundle.id}`);
        const idx = state.bundles.findIndex(x => x.id === bundle.id);
        if (idx !== -1) state.bundles[idx] = fullBundle;
        renderList();
      } catch (err) {
        toast("err", "Upload failed", err.message);
      }
    });
  }

  row.querySelectorAll(".btn-del-doc").forEach(btn => {
    btn.addEventListener("click", async () => {
      const docId = btn.dataset.doc;
      try {
        await api(`/documents/${docId}`, { method: "DELETE" });
        toast("ok", "Document removed");
        const fullBundle = await api(`/bundles/${bundle.id}`);
        const idx = state.bundles.findIndex(x => x.id === bundle.id);
        if (idx !== -1) state.bundles[idx] = fullBundle;
        renderList();
      } catch (err) {
        toast("err", "Delete failed", err.message);
      }
    });
  });
}

async function runVerification(bundleId) {
  if (state.running.has(bundleId)) return;
  state.running.add(bundleId);
  renderList();
  try {
    toast("info", "Evaluating Policy Rules", "Verifying BizFile, M&AA, ROM, and Board Resolution...");
    const res = await api(`/bundles/${bundleId}/verify`, { method: "POST" });
    toast(res.overall_verdict === "PASS" ? "ok" : "err", `Verdict: ${res.overall_verdict}`, res.summary);
    const full = await api(`/bundles/${bundleId}`);
    const idx = state.bundles.findIndex(x => x.id === bundleId);
    if (idx !== -1) state.bundles[idx] = full;
  } catch (err) {
    toast("err", "Verification error", err.message);
  } finally {
    state.running.delete(bundleId);
    renderList();
  }
}

document.addEventListener("DOMContentLoaded", init);
