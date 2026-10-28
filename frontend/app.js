/* ============================================================
   Wholesale Bank Policy Verification Dashboard (app.js)
   ============================================================ */
const API = "/api";

const state = {
  rules: [],
  bundles: [],
  filter: "",
  expanded: new Set(),
  running: new Set(),
  runningAll: false,
  collapsedPanels: new Set(),
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
    toast("info", "Batch Verification", "Evaluating all corporate files against 6 policy rules...");
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

function isMatchingDoc(doc, keywords, types) {
  const t = (doc.doc_type || "").toLowerCase();
  const f = " " + (doc.original_name || "").toLowerCase().replace(/[^a-z0-9]/g, " ") + " ";
  if (types.some(type => type.toLowerCase() === t)) return true;
  return keywords.some(k => {
    const cleanK = k.toLowerCase().replace(/[^a-z0-9]/g, " ").trim();
    if (!cleanK) return false;
    if (cleanK.length <= 2) {
      const regex = new RegExp(`\\b${cleanK}\\b`, "i");
      return regex.test(f);
    }
    return f.includes(" " + cleanK + " ") || f.includes(cleanK);
  });
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

  // Ultra-robust matching for the 7 document checklist items
  const hasBizfile = docs.some(d => isMatchingDoc(d, ["bizfile", "profile", "acra", "search", "coi", "business profile"], ["bizfile"]));
  const hasMaa = docs.some(d => isMatchingDoc(d, ["maa", "m aa", "m&aa", "memorandum", "articles", "constitution", "by laws", "m and a", "association"], ["maa"]));
  const hasRom = docs.some(d => isMatchingDoc(d, ["rom", "member", "members", "register of member", "register of members", "shareholder", "shareholding", "share register"], ["rom"]));
  const hasRod = docs.some(d => isMatchingDoc(d, ["rod", "director", "directors", "register of director", "register of directors", "director register"], ["rod"]));
  const hasIdDoc = docs.some(d => isMatchingDoc(d, ["passport", "nric", "fin", "national id", "identity card", "driving license", "driver license", "id", "identity", "identification", "ubo id", "director id", "license", "licence"], ["id_document"]));
  const hasPoaDoc = docs.some(d => isMatchingDoc(d, ["utility bill", "proof of address", "address proof", "residential address", "utility", "uttility", "electricity", "water bill", "telecom bill", "council tax", "tenancy agreement", "address", "poa", "bill", "bills", "statement", "tenancy", "telecom", "utilities"], ["proof_of_address"]));
  const hasIdAndPoa = hasIdDoc && hasPoaDoc;
  const hasUboDecl = docs.some(d => {
    // If it's an ID (like "UBO ID.jpg"), don't treat it as UBO Declaration Form!
    if (isMatchingDoc(d, ["passport", "nric", "fin", "id", "identity", "license"], ["id_document"])) return false;
    return isMatchingDoc(d, ["gldb", "declaration of ultimate", "ubo declaration", "beneficial owner", "beneficial ownership", "ubo"], ["ubo_declaration"]);
  });
  const hasBoard = docs.some(d => isMatchingDoc(d, ["board", "resolution", "mandate", "minutes", "signing mandate", "board resolution"], ["board_resolution"]));
  const hasSanction = docs.some(d => isMatchingDoc(d, ["sanction", "sanctions", "strategic goods", "scf", "dual-use", "trade compliance"], ["sanction_questionnaire"]));
  const hasInst = docs.some(d => isMatchingDoc(d, ["wolfsberg", "cbddq", "msb", "fund", "investment vehicle", "trustee"], ["institutional_questionnaire"]));
  const hasCdd = docs.some(d => isMatchingDoc(d, ["cdd", "edd", "nexus", "account purpose", "tax risk", "continuation", "sign-off"], ["cdd_edd_questionnaire"]));
  const hasTrans = docs.some(d => isMatchingDoc(d, ["translation", "sworn", "translator", "certified translation"], ["translation_certificate"]));
  const hasRiskCalc = docs.some(d => isMatchingDoc(d, ["risk", "calculator", "matrix", "score"], ["risk_calculator"]));
  const transDoc = docs.find(d => 
    isMatchingDoc(d, ["transaction", "transactions", "statement", "ledger", "listing", "throughput", "turnover", "txns", "tx"], ["transaction_listing"]) ||
    ((d.original_name && (d.original_name.toLowerCase().endsWith(".csv") || d.original_name.toLowerCase().endsWith(".xlsx") || d.original_name.toLowerCase().endsWith(".xls"))) &&
     !isMatchingDoc(d, ["risk", "calculator", "matrix", "score"], ["risk_calculator"]))
  );
  const hasTransList = !!transDoc;

  const isCollapsed = state.collapsedPanels.has(b.id);

  return `
    <div class="row-detail">
      <div class="detail-grid ${isCollapsed ? 'collapsed-left' : ''}">
        
        <!-- Left: Ingestion & Document Requirements Checklist (Collapsible) -->
        ${isCollapsed ? `
          <div class="panel-dock" title="Ingestion panel collapsed. Click to expand and view requirements & uploaded files.">
            <button class="panel-dock-btn btn-toggle-panel" data-bundle="${b.id}" title="Expand Ingestion & Documents Panel">
              <i data-lucide="panel-left-open" style="width:20px; height:20px; color:var(--blue);"></i>
              <span class="panel-dock-label">DOCUMENTS & CHECKLIST</span>
              <span class="badge ${docs.length > 0 ? 'badge-pass' : 'badge-na'}" style="font-size:10px; padding:2px 6px;">${docs.length} Files</span>
            </button>
            <label class="icon-btn" style="cursor:pointer; margin-top:14px;" title="Upload documents into folder">
              <i data-lucide="upload-cloud"></i>
              <input type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.webp,.csv,.xlsx,.xls" class="doc-upload-input" data-bundle="${b.id}" style="display:none" />
            </label>
          </div>
        ` : `
          <div class="card-box">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:14px; gap:8px;">
              <div>
                <h4 style="font-weight:700; font-size:14px; color:var(--navy); display:flex; align-items:center; gap:6px;">
                  <i data-lucide="folder-check" style="color:var(--blue);"></i> Ingest Corporate Document Folder
                </h4>
                <p style="font-size:11.5px; color:var(--muted); margin-top:2px;">Wholesale Bank policy document requirements across 10 validation modules:</p>
              </div>
              <div style="display:flex; align-items:center; gap:6px;">
                <label class="btn btn-sm btn-primary" style="cursor:pointer" title="Upload folder or multiple documents">
                  <i data-lucide="upload-cloud"></i> Ingest Files
                  <input type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.webp,.csv,.xlsx,.xls" class="doc-upload-input" data-bundle="${b.id}" style="display:none" />
                </label>
                <button class="btn btn-sm btn-ghost btn-toggle-panel" data-bundle="${b.id}" title="Collapse panel to expand check analysis area" style="display:flex; align-items:center; gap:4px; padding:6px 9px;">
                  <i data-lucide="panel-left-close"></i>
                  <span>Collapse</span>
                </button>
              </div>
            </div>

            <!-- Document Requirement Checkpoints (Tabularly Aligned) -->
            <div class="req-table-wrap">
              <table class="req-table">
                <thead>
                  <tr>
                    <th class="req-col-icon"></th>
                    <th>File Required</th>
                    <th>Policy Scope / Condition</th>
                    <th class="req-col-status">Ingestion Status</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td class="req-col-icon"><i data-lucide="${hasBizfile ? 'check-circle-2' : 'alert-circle'}" class="${hasBizfile ? 'text-pass' : 'text-warn'}" style="width:13px; height:13px;"></i></td>
                    <td class="req-col-name">1. Business Profile / ACRA BizFile</td>
                    <td class="req-col-spec"><span class="spec-pill">Last 12 Months</span></td>
                    <td class="req-col-status"><span class="badge ${hasBizfile ? 'badge-pass' : 'badge-warn'}" style="font-size:10px; padding:2px 7px;">${hasBizfile ? 'Provided' : 'Required'}</span></td>
                  </tr>
                  <tr>
                    <td class="req-col-icon"><i data-lucide="${hasMaa ? 'check-circle-2' : 'alert-circle'}" class="${hasMaa ? 'text-pass' : 'text-warn'}" style="width:13px; height:13px;"></i></td>
                    <td class="req-col-name">2. Memorandum & Articles of Association (M&AA)</td>
                    <td class="req-col-spec"><span class="spec-pill">CTC Certified</span></td>
                    <td class="req-col-status"><span class="badge ${hasMaa ? 'badge-pass' : 'badge-warn'}" style="font-size:10px; padding:2px 7px;">${hasMaa ? 'Provided' : 'Required'}</span></td>
                  </tr>
                  <tr>
                    <td class="req-col-icon"><i data-lucide="${hasRom ? 'check-circle-2' : 'alert-circle'}" class="${hasRom ? 'text-pass' : 'text-warn'}" style="width:13px; height:13px;"></i></td>
                    <td class="req-col-name">3. Register of Members (ROM)</td>
                    <td class="req-col-spec"><span class="spec-pill">CTC Certified</span></td>
                    <td class="req-col-status"><span class="badge ${hasRom ? 'badge-pass' : 'badge-warn'}" style="font-size:10px; padding:2px 7px;">${hasRom ? 'Provided' : 'Required'}</span></td>
                  </tr>
                  <tr>
                    <td class="req-col-icon"><i data-lucide="${hasRod ? 'check-circle-2' : 'alert-circle'}" class="${hasRod ? 'text-pass' : 'text-warn'}" style="width:13px; height:13px;"></i></td>
                    <td class="req-col-name">4. Register of Directors (ROD)</td>
                    <td class="req-col-spec"><span class="spec-pill">Structure & Controllers</span></td>
                    <td class="req-col-status"><span class="badge ${hasRod ? 'badge-pass' : 'badge-warn'}" style="font-size:10px; padding:2px 7px;">${hasRod ? 'Provided' : 'Required'}</span></td>
                  </tr>
                  <tr>
                    <td class="req-col-icon"><i data-lucide="${hasIdAndPoa ? 'check-circle-2' : 'alert-circle'}" class="${hasIdAndPoa ? 'text-pass' : 'text-warn'}" style="width:13px; height:13px;"></i></td>
                    <td class="req-col-name">5. Director / UBO ID Documents & Address Proof</td>
                    <td class="req-col-spec"><span class="spec-pill">Non-Expired ID + Utility Bill</span></td>
                    <td class="req-col-status">
                      <span class="badge ${hasIdAndPoa ? 'badge-pass' : 'badge-warn'}" style="font-size:10px; padding:2px 7px;">
                        ${hasIdAndPoa ? 'Provided' : (hasIdDoc ? 'Missing Address Proof' : (hasPoaDoc ? 'Missing Passport / ID' : 'Required'))}
                      </span>
                    </td>
                  </tr>
                  <tr>
                    <td class="req-col-icon"><i data-lucide="${hasUboDecl ? 'check-circle-2' : 'alert-circle'}" class="${hasUboDecl ? 'text-pass' : 'text-warn'}" style="width:13px; height:13px;"></i></td>
                    <td class="req-col-name">6. GLDB UBO Declaration (Mar 2026)</td>
                    <td class="req-col-spec"><span class="spec-pill">Nominee / Complex</span></td>
                    <td class="req-col-status"><span class="badge ${hasUboDecl ? 'badge-pass' : 'badge-warn'}" style="font-size:10px; padding:2px 7px;">${hasUboDecl ? 'Provided' : 'Required'}</span></td>
                  </tr>
                  <tr>
                    <td class="req-col-icon"><i data-lucide="${hasBoard ? 'check-circle-2' : 'info'}" class="${hasBoard ? 'text-pass' : 'text-na'}" style="width:13px; height:13px;"></i></td>
                    <td class="req-col-name">7. Board Resolution & Mandate</td>
                    <td class="req-col-spec"><span class="spec-pill">Where applicable, CTC</span></td>
                    <td class="req-col-status"><span class="badge ${hasBoard ? 'badge-pass' : 'badge-na'}" style="font-size:10px; padding:2px 7px;">${hasBoard ? 'Provided' : 'Conditional'}</span></td>
                  </tr>
                  <tr>
                    <td class="req-col-icon"><i data-lucide="${hasSanction ? 'check-circle-2' : 'info'}" class="${hasSanction ? 'text-pass' : 'text-na'}" style="width:13px; height:13px;"></i></td>
                    <td class="req-col-name">8. Sanction Questionnaire</td>
                    <td class="req-col-spec"><span class="spec-pill">GLDB Internal (Descr. 10)</span></td>
                    <td class="req-col-status"><span class="badge ${hasSanction ? 'badge-pass' : 'badge-na'}" style="font-size:10px; padding:2px 7px;">${hasSanction ? 'Provided' : 'Conditional'}</span></td>
                  </tr>
                  <tr>
                    <td class="req-col-icon"><i data-lucide="${hasInst ? 'check-circle-2' : 'info'}" class="${hasInst ? 'text-pass' : 'text-na'}" style="width:13px; height:13px;"></i></td>
                    <td class="req-col-name">9. Institutional Questionnaire</td>
                    <td class="req-col-spec"><span class="spec-pill">Wolfsberg / MSB / Funds (Descr. 12)</span></td>
                    <td class="req-col-status"><span class="badge ${hasInst ? 'badge-pass' : 'badge-na'}" style="font-size:10px; padding:2px 7px;">${hasInst ? 'Provided' : 'Conditional'}</span></td>
                  </tr>
                  <tr>
                    <td class="req-col-icon"><i data-lucide="${hasCdd ? 'check-circle-2' : 'alert-circle'}" class="${hasCdd ? 'text-pass' : 'text-warn'}" style="width:13px; height:13px;"></i></td>
                    <td class="req-col-name">10. CDD / EDD Questionnaire</td>
                    <td class="req-col-spec"><span class="spec-pill">Nexus, Tax & Sign-Off</span></td>
                    <td class="req-col-status"><span class="badge ${hasCdd ? 'badge-pass' : 'badge-warn'}" style="font-size:10px; padding:2px 7px;">${hasCdd ? 'Provided' : 'Required'}</span></td>
                  </tr>
                  <tr>
                    <td class="req-col-icon"><i data-lucide="shield-check" class="text-blue" style="width:13px; height:13px;"></i></td>
                    <td class="req-col-name">11. MAS Central Bank Directory</td>
                    <td class="req-col-spec"><span class="spec-pill">Live FID Registry Cross-Check</span></td>
                    <td class="req-col-status"><span class="badge" style="background:#e0f2fe; color:#0369a1; border:1px solid #bae6fd; font-size:10px; padding:2px 7px;">Live Registry Crawl</span></td>
                  </tr>
                  <tr>
                    <td class="req-col-icon"><i data-lucide="${(hasRiskCalc || (hasBizfile && (hasUboDecl || hasId))) ? 'check-circle-2' : 'info'}" class="${(hasRiskCalc || (hasBizfile && (hasUboDecl || hasId))) ? 'text-pass' : 'text-blue'}" style="width:13px; height:13px;"></i></td>
                    <td class="req-col-name">12. Risk Calculator Engine</td>
                    <td class="req-col-spec"><span class="spec-pill">Customer & UBO Scorecard</span></td>
                    <td class="req-col-status">
                      <span class="badge ${hasRiskCalc ? 'badge-pass' : (hasBizfile && (hasUboDecl || hasId)) ? 'badge-info' : 'badge-na'}" style="font-size:10px; padding:2px 7px;">
                        ${hasRiskCalc ? 'Provided (.xlsx)' : (hasBizfile && (hasUboDecl || hasId)) ? 'Auto-Calculated' : 'Ready (KYC Files)'}
                      </span>
                    </td>
                  </tr>
                  <tr>
                    <td class="req-col-icon"><i data-lucide="globe" class="text-blue" style="width:13px; height:13px;"></i></td>
                    <td class="req-col-name">13. Client Official Website & OSINT Audit</td>
                    <td class="req-col-spec"><span class="spec-pill">Domain Age, Services & Activity</span></td>
                    <td class="req-col-status"><span class="badge" style="background:#e0f2fe; color:#0369a1; border:1px solid #bae6fd; font-size:10px; padding:2px 7px;">Playwright + RDAP</span></td>
                  </tr>
                  <tr>
                    <td class="req-col-icon"><i data-lucide="${hasTransList ? 'check-circle-2' : 'alert-circle'}" class="${hasTransList ? 'text-pass' : 'text-warn'}" style="width:13px; height:13px;"></i></td>
                    <td class="req-col-name">
                      14. Past 6-Month Transaction Listing
                      ${hasTransList ? `<div style="font-size:10px; color:#16a34a; font-weight:600; margin-top:2px;">File: ${esc(transDoc.original_name)}</div>` : ''}
                    </td>
                    <td class="req-col-spec"><span class="spec-pill">Excel .xlsx / CSV (21 Fields)</span></td>
                    <td class="req-col-status">
                      <span class="badge ${hasTransList ? 'badge-pass' : 'badge-warn'}" style="font-size:10px; padding:2px 7px;">
                        ${hasTransList ? `Ingested (${(transDoc.original_name || '').split('.').pop().toUpperCase()})` : 'Not Ingested (Required)'}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- Uploaded Documents Ingested List -->
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; margin-top:16px;">
              <h5 style="font-size:12px; font-weight:700; color:var(--navy);">Ingested Files on Record (${docs.length})</h5>
              <span style="font-size:10.5px; color:#64748b; font-weight:600;">${docs.filter(d => d.is_ctc).length} CTC Verified</span>
            </div>
            <div class="doc-list" style="display:flex; flex-direction:column; gap:8px;">
              ${docs.length === 0 ? '<div style="padding:16px; text-align:center; background:#fff; border:1px dashed #cbd5e1; border-radius:6px; color:#64748b; font-size:12px;">Click "Ingest Files" to upload client document PDFs or ID images.</div>' : ''}
              ${docs.map(d => {
                const ext = (d.original_name || '').toLowerCase();
                const isSheet = ext.endsWith('.xlsx') || ext.endsWith('.xls') || ext.endsWith('.csv');
                return `
                <div class="doc-item" style="display:flex; justify-content:space-between; align-items:center; padding:8px 12px; background:#fff; border:1px solid #e2e8f0; border-radius:6px;">
                  <div style="display:flex; align-items:center; gap:8px;">
                    <i data-lucide="${d.content_type?.startsWith('image/') ? 'image' : (isSheet ? 'file-spreadsheet' : 'file-text')}" style="color:var(--blue)"></i>
                    <div>
                      <div style="font-weight:600; font-size:12.5px; color:var(--navy);">${esc(d.original_name)}</div>
                      <div style="font-size:11px; color:#64748b;">
                        Detected: <b style="color:var(--navy-2)">${esc(d.doc_type)}</b> 
                        ${d.is_ctc ? '· <span style="color:#16a34a; font-weight:700;">CTC Verified ✓</span>' : '· <span style="color:#94a3b8;">Standard Copy</span>'}
                      </div>
                    </div>
                  </div>
                  <button class="icon-btn btn-del-doc" data-doc="${d.id}" title="Remove file"><i data-lucide="trash-2"></i></button>
                </div>
              `;}).join('')}
            </div>
          </div>
        `}

        <!-- Right: Policy Check Breakdown with Itemized File Cards -->
        <div class="card-box">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px;">
            <div style="display:flex; align-items:center; gap:8px;">
              ${isCollapsed ? `
                <button class="btn btn-sm btn-ghost btn-toggle-panel" data-bundle="${b.id}" title="Expand Ingestion & Documents Panel" style="display:flex; align-items:center; gap:5px; font-weight:700;">
                  <i data-lucide="panel-left-open" style="width:14px; height:14px; color:var(--blue);"></i>
                  <span>Show Documents & Checklist (${docs.length})</span>
                </button>
              ` : ''}
              <h4 style="font-weight:700; font-size:14px; color:var(--navy); display:flex; align-items:center; gap:8px;">
                <i data-lucide="shield-check" style="color:var(--blue)"></i> Wholesale Bank Policy Verification & Audit
              </h4>
            </div>
            ${run && run.elapsed_seconds ? `
              <div style="display:flex; align-items:center; gap:6px;">
                <span class="badge" style="background:#f1f5f9; color:#475569; border:1px solid #cbd5e1; font-size:11.5px; font-weight:600; padding:4px 10px; border-radius:6px; display:inline-flex; align-items:center; gap:4px;">
                  ⏱️ Latency: <b style="color:var(--navy);">${run.elapsed_seconds.toFixed(2)}s</b>
                </span>
              </div>
            ` : ''}
          </div>

          ${!run ? `
            <div style="padding:28px 20px; text-align:center; background:#f8fafc; border:1px dashed #cbd5e1; border-radius:8px; color:#64748b; font-size:13px;">
              <i data-lucide="shield-alert" style="width:36px; height:36px; color:#94a3b8; margin-bottom:8px; display:inline-block;"></i>
              <div style="font-weight:700; color:var(--navy); margin-bottom:4px;">No Validation Results Yet</div>
              <div>Click <b>Run Validation</b> to execute multi-modal AI Vision & deterministic policy validation across all 14 wholesale checks.</div>
            </div>
          ` : `
            <!-- Executive Summary Card -->
            ${(() => {
              const exec = run.executive_summary || {
                compliance_percentage: Math.round(((run.results || []).filter(x => x.verdict === 'PASS').length / ((run.results || []).length || 14)) * 100),
                passed_count: (run.results || []).filter(x => x.verdict === 'PASS').length,
                total_count: (run.results || []).length || 14,
                risk_tier: run.overall_verdict === 'PASS' ? 'LOW' : 'HIGH',
                narrative: run.summary || 'Validation completed across wholesale policy checks.',
                recommendation: run.overall_verdict === 'PASS' ? 'Approved for Wholesale Bank KYC Onboarding' : 'Action Required: Remediate flagged non-compliance items before onboarding.'
              };
              const isPass = run.overall_verdict === 'PASS';
              return `
              <div class="exec-summary-card ${isPass ? 'pass' : 'fail'}">
                <div class="exec-head">
                  <div class="exec-title">
                    <i data-lucide="${isPass ? 'shield-check' : 'shield-alert'}" style="color:${isPass ? 'var(--pass)' : 'var(--fail)'}; width:18px; height:18px;"></i>
                    Executive Compliance Summary
                  </div>
                  <div style="display:flex; align-items:center; gap:8px;">
                    <span class="badge ${isPass ? 'badge-pass' : 'badge-fail'}" style="font-size:11.5px; padding:3px 10px;">
                      VERDICT: ${run.overall_verdict}
                    </span>
                    <span class="badge" style="background:#e0f2fe; color:#0369a1; border:1px solid #bae6fd; font-size:11px;">
                      Risk Tier: <b>${esc(exec.risk_tier || 'Standard')}</b>
                    </span>
                    ${run.elapsed_seconds ? `
                      <span class="badge" style="background:#f8fafc; color:#475569; border:1px solid #e2e8f0; font-size:11px; font-weight:600;">
                        ⏱️ ${run.elapsed_seconds.toFixed(2)}s
                      </span>
                    ` : ''}
                  </div>
                </div>

                <div class="kri-strip">
                  <div class="kri-box">
                    <span class="kri-box-lbl">Compliance Score</span>
                    <span class="kri-box-val" style="color:${(exec.compliance_percentage || 0) >= 80 ? 'var(--pass)' : 'var(--fail)'};">
                      ${exec.compliance_percentage || 0}%
                    </span>
                  </div>
                  <div class="kri-box">
                    <span class="kri-box-lbl">Checks Passed</span>
                    <span class="kri-box-val" style="color:${exec.passed_count === exec.total_count ? 'var(--pass)' : (isPass ? 'var(--navy)' : 'var(--fail)')};">
                      ${exec.passed_count} / ${exec.total_count}
                    </span>
                  </div>
                  <div class="kri-box">
                    <span class="kri-box-lbl">Audit Status</span>
                    <span class="kri-box-val" style="color:var(--navy);">
                      ${isPass ? 'Audit Cleared' : 'Deficiencies Found'}
                    </span>
                  </div>
                  <div class="kri-box">
                    <span class="kri-box-lbl">Cross-Checked Files</span>
                    <span class="kri-box-val" style="color:var(--navy);">
                      ${docs.length} Documents
                    </span>
                  </div>
                </div>

                <div class="exec-narrative">
                  <b>Executive Assessment:</b> ${esc(exec.narrative || run.summary || '')}
                </div>

                <div class="exec-rec-box ${isPass ? 'pass' : 'fail'}">
                  <i data-lucide="${isPass ? 'check-circle' : 'alert-circle'}" style="width:16px; height:16px; flex-shrink:0;"></i>
                  <span><b>Actionable Recommendation:</b> ${esc(exec.recommendation || '')}</span>
                </div>
              </div>
              `;
            })()}

            <!-- Checks List -->
            <div class="checks-list" style="display:flex; flex-direction:column; gap:12px;">
              ${(() => {
                const checkOrder = [
                  "CHK_01_BIZFILE", "CHK_02_INCORP", "CHK_03_CONST", "CHK_04_CORP_STRUCT",
                  "CHK_05_ID_EXPIRY", "CHK_06_UBO_COMPLEX", "CHK_07_SANCTIONS", "CHK_08_INSTITUTIONAL",
                  "CHK_09_CDD_EDD", "CHK_10_INGESTION_QUALITY", "CHK_11_MAS_REGISTER", "CHK_12_RISK_CALCULATOR",
                  "CHK_13_DIGITAL_FOOTPRINT", "CHK_14_TRANSACTION_REVIEW"
                ];
                const sortedResults = (run.results || []).slice().sort((a, b) => {
                  const idxA = checkOrder.indexOf(a.check_id);
                  const idxB = checkOrder.indexOf(b.check_id);
                  if (idxA !== -1 && idxB !== -1) return idxA - idxB;
                  if (idxA !== -1) return -1;
                  if (idxB !== -1) return 1;
                  return a.check_id.localeCompare(b.check_id);
                });
                return sortedResults.map(r => {
                  const isCheckPass = r.verdict === 'PASS';
                  const evalFiles = r.evaluated_files || [];
                  const subChecks = r.sub_checks || [];
                  const passedSubCount = subChecks.filter(s => s.verdict === 'PASS').length;
                  return `
                  <div class="check-card ${isCheckPass ? 'pass' : 'fail'}">
                    
                    <!-- Check Header -->
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                      <span style="font-weight:700; color:var(--navy); font-size:13px;">${esc(r.check_id)}: ${esc(r.rule_name)}</span>
                      <span class="badge ${isCheckPass ? 'badge-pass' : 'badge-fail'}">${r.verdict}</span>
                    </div>
                    
                    <!-- Check Overall Evidence Summary -->
                    <div style="font-size:12px; color:#334155; line-height:1.45; margin-bottom:8px;">
                      <b>Evaluation Summary:</b> ${esc(r.evidence)}
                    </div>

                    <!-- Cross-Checked Files Section -->
                    <div class="eval-files-section">
                      <div class="eval-files-header">
                        <i data-lucide="layers" style="width:12px; height:12px;"></i>
                        Cross-Checked Evidence Files (${evalFiles.length})
                      </div>
                      ${evalFiles.length > 0 ? evalFiles.map(f => `
                        <div class="eval-file-chip ${f.verdict === 'PASS' ? 'file-pass' : 'file-fail'}">
                          <span style="display:flex; align-items:center; gap:5px;">
                            <i data-lucide="${f.verdict === 'PASS' ? 'check' : 'x'}" style="color:${f.verdict === 'PASS' ? '#16a34a' : '#dc2626'}; width:12px; height:12px;"></i>
                            <b>${esc(f.doc_name)}</b> <span style="color:#64748b; font-size:10.5px;">(${esc(f.doc_type)})</span>
                          </span>
                          <span style="font-size:10.5px; color:${f.verdict === 'PASS' ? '#15803d' : '#b91c1c'}; font-weight:600;">
                            ${esc(f.details)}
                          </span>
                        </div>
                      `).join('') : `
                        <div style="font-size:11px; color:#64748b; font-style:italic; padding:2px 4px;">
                          Cross-checked against corporate client master dossier & official registry sources.
                        </div>
                      `}
                    </div>

                    <!-- Granular Sub-Checks Dropdown Accordion -->
                    ${subChecks.length > 0 ? `
                      <details class="subcheck-accordion" ${!isCheckPass ? 'open' : ''}>
                        <summary>
                          <span style="display:flex; align-items:center; gap:6px;">
                            <i data-lucide="list-checks" style="width:13px; height:13px; color:var(--blue);"></i>
                            Sub-Checks Verification (${passedSubCount}/${subChecks.length} Passed)
                          </span>
                          <span style="font-size:10.5px; color:#64748b; font-weight:600;">
                            ${passedSubCount === subChecks.length ? 'All Compliant ✓' : `${subChecks.length - passedSubCount} Action Needed ⚠️`} · Click to view ▼
                          </span>
                        </summary>
                        <div class="subcheck-content">
                          ${subChecks.map(sc => {
                            const scPass = sc.verdict === 'PASS';
                            return `
                            <div class="subcheck-item ${scPass ? 'pass' : 'fail'}">
                              <div class="subcheck-header">
                                <span class="subcheck-title">
                                  <code style="font-size:10px; background:#e2e8f0; padding:1px 4px; border-radius:3px;">${esc(sc.sub_id)}</code>
                                  ${esc(sc.name)}
                                </span>
                                <span class="${scPass ? 'badge-sub-pass' : 'badge-sub-fail'}">
                                  ${sc.verdict}
                                </span>
                              </div>
                              <div class="subcheck-desc">
                                ${esc(sc.details || sc.description || '')}
                              </div>
                            </div>
                            `;
                          }).join('')}
                        </div>
                      </details>
                    ` : ''}

                    <!-- Reason & Priority Tags -->
                    ${r.reason_code ? `
                      <div style="margin-top:8px; font-size:11.5px; font-weight:700; color:#dc2626; display:flex; gap:12px;">
                        <span>Failure Reason: <mark style="background:#fee2e2; color:#dc2626; padding:1px 5px; border-radius:4px;">${esc(r.reason_code)}</mark></span>
                        <span>Priority: <mark style="background:#fee2e2; color:#dc2626; padding:1px 5px; border-radius:4px;">${esc(r.priority)}</mark></span>
                      </div>
                    ` : ''}

                  </div>
                  `;
                }).join('');
              })()}
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

  row.querySelectorAll(".subcheck-accordion").forEach(acc => {
    acc.addEventListener("toggle", () => icons());
  });

  row.querySelectorAll(`.btn-toggle-panel[data-bundle="${bundle.id}"]`).forEach(btn => {
    btn.addEventListener("click", () => {
      if (state.collapsedPanels.has(bundle.id)) {
        state.collapsedPanels.delete(bundle.id);
      } else {
        state.collapsedPanels.add(bundle.id);
      }
      renderList();
    });
  });
}

async function runVerification(bundleId) {
  if (state.running.has(bundleId)) return;
  state.running.add(bundleId);
  renderList();
  try {
    toast("info", "Evaluating Policy Rules", "Verifying wholesale compliance checks across ACRA BizFile, M&AA, ROM, ROD, UBO, Sanctions, MAS, and Transactions...");
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

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
