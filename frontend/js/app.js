// ============================================================================
// AGENTIC LEGAL ASSISTANT — MAIN APP CONTROLLER & VIEW ROUTER
// Manages global shell, view switching, active case state & dashboard telemetry
// ============================================================================

const APP_STATE = {
  currentView: "dashboard",
  caseId: null,
  documents: [],
  outputs: null,
  activities: [],
};

// --- View Router ---
function switchView(viewName) {
  APP_STATE.currentView = viewName;

  // Update navigation pills
  document.querySelectorAll(".nav-item").forEach((btn) => {
    if (btn.dataset.view === viewName) {
      btn.classList.add("active");
      btn.setAttribute("aria-current", "page");
    } else {
      btn.classList.remove("active");
      btn.removeAttribute("aria-current");
    }
  });

  // Toggle view containers
  document.querySelectorAll(".view-section").forEach((sec) => {
    if (sec.id === `view-${viewName}`) {
      sec.hidden = false;
      sec.classList.add("is-active");
    } else {
      sec.hidden = true;
      sec.classList.remove("is-active");
    }
  });

  // Update breadcrumb
  const breadcrumbCurrent = document.getElementById("breadcrumbCurrent");
  if (breadcrumbCurrent) {
    const titles = {
      dashboard: "Dashboard Overview",
      cases: "Case Management",
      documents: "Evidence & Documents",
      research: "Legal Authority Research",
      drafting: "Automated Petition Drafting",
      assistant: "Grounded AI Legal Assistant",
      verification: "Verification & Audit Center",
      settings: "Workspace Diagnostics",
    };
    breadcrumbCurrent.textContent = titles[viewName] || "Workspace";
  }

  // View-specific on-open refreshes
  if (viewName === "dashboard") updateDashboardMetrics();
  if (viewName === "cases") renderCasesList();
  if (viewName === "verification" && typeof refreshReport === "function") refreshReport();
  if (viewName === "drafting" && typeof refreshDraft === "function") refreshDraft();
}

// --- Activity Feed Logger ---
function logActivity(title, desc, type = "info") {
  const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  APP_STATE.activities.unshift({ title, desc, type, time });
  if (APP_STATE.activities.length > 25) APP_STATE.activities.pop();
  renderActivityFeed();
}

function renderActivityFeed() {
  const container = document.getElementById("activityFeed");
  if (!container) return;
  container.replaceChildren();

  if (!APP_STATE.activities.length) {
    container.append(
      el("div", "No recent case activities recorded in this session.", "empty-activity-note")
    );
    return;
  }

  APP_STATE.activities.slice(0, 7).forEach((act) => {
    const item = el("div", undefined, `activity-item activity-${act.type}`);
    const dot = el("div", undefined, "activity-dot");
    const content = el("div", undefined, "activity-content");
    const header = el("div", undefined, "activity-header");
    header.append(el("strong", act.title), el("span", act.time, "activity-time"));
    content.append(header, el("p", act.desc, "activity-desc"));
    item.append(dot, content);
    container.append(item);
  });
}

// --- Dashboard Telemetry & Summary ---
function updateDashboardMetrics() {
  const docs = APP_STATE.documents || [];
  const totalPages = docs.reduce((acc, d) => acc + (d.page_count || 0), 0);
  const totalChunks = docs.reduce((acc, d) => acc + (d.chunk_count || 0), 0);
  const totalFacts = docs.reduce((acc, d) => acc + Object.keys(d.facts || {}).length, 0);

  // Update counters
  const setTxt = (id, val) => {
    const elem = document.getElementById(id);
    if (elem) elem.textContent = String(val);
  };

  setTxt("statDocsCount", docs.length);
  setTxt("statPagesCount", totalPages);
  setTxt("statChunksCount", totalChunks);
  setTxt("statFactsCount", totalFacts);
  setTxt("statCaseIdDisplay", APP_STATE.caseId || "No active case");

  // Readiness & Contradictions from outputs
  const out = APP_STATE.outputs || {};
  const mi = out.missing_info;
  const contra = out.contradictions;

  if (mi && mi.readiness) {
    setTxt("statReadinessPct", `${mi.readiness.percent}%`);
    const bar = document.getElementById("statReadinessBar");
    if (bar) bar.style.width = `${mi.readiness.percent}%`;
  } else {
    setTxt("statReadinessPct", docs.length ? "Pending" : "0%");
    const bar = document.getElementById("statReadinessBar");
    if (bar) bar.style.width = docs.length ? "30%" : "0%";
  }

  const contraCount = (contra && contra.items) ? contra.items.length : 0;
  setTxt("statContraCount", contraCount);

  // Render recent cases table on dashboard
  renderDashboardCasesTable();
}

function renderDashboardCasesTable() {
  const container = document.getElementById("dashCasesList");
  if (!container) return;
  container.replaceChildren();

  if (!APP_STATE.documents.length) {
    container.append(
      el("div", "No documents uploaded yet. Upload a case record PDF to begin analysis.", "empty-state-p")
    );
    return;
  }

  const table = el("table", undefined, "legal-table");
  const thead = el("thead");
  const hrow = el("tr");
  ["Document ID", "Title / Record", "Type", "Pages", "Passages", "Extracted Facts"].forEach((h) => {
    hrow.append(el("th", h));
  });
  thead.append(hrow);
  table.append(thead);

  const tbody = el("tbody");
  APP_STATE.documents.forEach((doc) => {
    const row = el("tr");
    const dId = el("td");
    dId.append(el("span", doc.doc_id, "badge-doc-id"));

    const fn = el("td");
    fn.append(el("strong", doc.filename));

    const dt = el("td");
    dt.append(el("span", doc.document_type || "Legal Record", "badge-pill badge-neutral"));

    const p = el("td", String(doc.page_count));
    const ch = el("td", String(doc.chunk_count));
    const fCount = el("td", `${Object.keys(doc.facts || {}).length} facts`);

    row.append(dId, fn, dt, p, ch, fCount);
    tbody.append(row);
  });
  table.append(tbody);
  container.append(table);
}

function renderCasesList() {
  const container = document.getElementById("casesDirectoryList");
  if (!container) return;
  container.replaceChildren();

  const caseCard = el("div", undefined, "case-overview-card");
  const header = el("div", undefined, "case-card-header");
  const titleGroup = el("div");
  titleGroup.append(
    el("span", APP_STATE.caseId ? "ACTIVE CASE" : "STANDBY", "badge-pill badge-primary"),
    el("h3", APP_STATE.caseId ? `Matter ${APP_STATE.caseId}` : "No Active Matter")
  );
  header.append(titleGroup);

  const metaRow = el("div", undefined, "case-card-meta-row");
  metaRow.append(
    el("div", `Documents: ${APP_STATE.documents.length}`, "meta-item"),
    el("div", `Status: ${APP_STATE.documents.length ? "Under Examination" : "Draft"}`, "meta-item"),
    el("div", "Jurisdiction: Saket District / Delhi", "meta-item")
  );

  const actions = el("div", undefined, "case-card-actions");
  const btnDoc = el("button", "Manage Documents", "btn btn-secondary btn-sm");
  btnDoc.addEventListener("click", () => switchView("documents"));
  const btnDraft = el("button", "Go to Drafting", "btn btn-primary btn-sm");
  btnDraft.addEventListener("click", () => switchView("drafting"));
  const btnAudit = el("button", "Open Verification", "btn btn-secondary btn-sm");
  btnAudit.addEventListener("click", () => switchView("verification"));

  actions.append(btnDoc, btnDraft, btnAudit);
  caseCard.append(header, metaRow, actions);
  container.append(caseCard);
}

// --- Setup Navigation Event Handlers ---
document.addEventListener("DOMContentLoaded", () => {
  // Navigation tabs
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const target = btn.dataset.view;
      if (target) switchView(target);
    });
  });

  // Quick Action Buttons
  const qaUpload = document.getElementById("qaUpload");
  if (qaUpload) qaUpload.addEventListener("click", () => switchView("documents"));

  const qaAnalyze = document.getElementById("qaAnalyze");
  if (qaAnalyze) {
    qaAnalyze.addEventListener("click", () => {
      switchView("verification");
      const aBtn = document.getElementById("analyzeBtn");
      if (aBtn && !aBtn.disabled) aBtn.click();
    });
  }

  const qaDraft = document.getElementById("qaDraft");
  if (qaDraft) qaDraft.addEventListener("click", () => switchView("drafting"));

  const qaChat = document.getElementById("qaChat");
  if (qaChat) qaChat.addEventListener("click", () => switchView("assistant"));

  const qaResearch = document.getElementById("qaResearch");
  if (qaResearch) qaResearch.addEventListener("click", () => switchView("research"));

  // Initial Activity Log
  logActivity("Workspace initialized", "Connected to local case storage engine.", "info");

  // Sync state on case-changed
  document.addEventListener("case-changed", async (e) => {
    APP_STATE.caseId = e.detail && e.detail.caseId;
    const chip = document.getElementById("topCaseChip");
    if (chip) chip.textContent = APP_STATE.caseId || "No active case";
    logActivity("Case updated", `Active matter identifier: ${APP_STATE.caseId}`, "success");
    await syncFullState();
  });
});

async function syncFullState() {
  try {
    const res = await fetch("/case?full=1");
    if (!res.ok) return;
    const store = await res.json();
    APP_STATE.caseId = store.case_id;
    APP_STATE.documents = store.documents || [];
    APP_STATE.outputs = store.outputs || {};
    updateDashboardMetrics();
    renderCasesList();
  } catch (err) {
    console.error("State sync error:", err);
  }
}
