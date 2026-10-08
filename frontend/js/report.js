// ============================================================================
// AGENTIC LEGAL ASSISTANT — CASE VERIFICATION & CONTRADICTION AUDIT
// Missing-information matrix, readiness score, conflict inspector
// ============================================================================

const draftTypeSel = document.getElementById("draftType");
const analyzeBtn = document.getElementById("analyzeBtn");
const reportStatus = document.getElementById("reportStatus");
const reportEl = document.getElementById("report");

function badge(text, cls) {
  return el("span", text, `badge-pill ${cls}`);
}

function sourceLine(chunkId, quote, value) {
  const box = el("div", undefined, "source-evidence-item");
  if (value !== undefined) box.append(el("strong", `${value} `));
  box.append(cidButton(chunkId, quote));
  if (quote) box.append(el("div", `"${quote}"`, "evidence-quote-snippet"));
  return box;
}

function renderMissing(mi) {
  const wrap = el("div", undefined, "verification-block");
  const r = mi.readiness;

  // Header & Readiness Summary Card
  const summaryCard = el("div", undefined, "readiness-summary-card");
  const sTop = el("div", undefined, "readiness-card-top");
  sTop.append(
    el("div", undefined).appendChild(
      el("span", "EVIDENTIARY READINESS GAUGE", "eyebrow-label")
    ).parentElement,
    el("span", `${r.percent}% Ready`, `badge-pill ${r.percent >= 70 ? "badge-success" : "badge-warn"}`)
  );
  sTop.querySelector("div").append(el("h3", `Matter Readiness for ${mi.label}`));
  summaryCard.append(sTop);

  const statusText = el(
    "p",
    `${r.required_found} of ${r.required_total} essential elements satisfied (${r.percent}%). ${r.status}`,
    "readiness-description"
  );
  summaryCard.append(statusText);

  // Modern progress bar
  const bar = el("div", undefined, "legal-progress-bar");
  const fill = el("div", undefined, "progress-fill");
  fill.style.width = `${r.percent}%`;
  if (r.percent >= 70) fill.classList.add("fill-success");
  bar.append(fill);
  summaryCard.append(bar);

  wrap.append(summaryCard);

  // Counsel guidance / clarifying questions
  if (mi.questions && mi.questions.length) {
    const qBox = el("div", undefined, "counsel-questions-box");
    const qTitle = el("div", undefined, "questions-header");
    qTitle.append(icon("alertTriangle", "icon-warn"), el("strong", "Counsel Action Items & Clarifications Needed"));
    qBox.append(qTitle);

    const ul = el("ul", undefined, "counsel-questions-list");
    mi.questions.forEach((q) => ul.append(el("li", q)));
    qBox.append(ul);
    wrap.append(qBox);
  }

  // Missing Information & Extracted Facts Matrix
  const tableTitle = el("div", undefined, "section-subhead");
  tableTitle.append(el("h4", "Requisite Elements Verification Matrix"));
  wrap.append(tableTitle);

  const tableWrap = el("div", undefined, "table-responsive");
  const table = el("table", undefined, "legal-table");
  const head = el("tr");
  ["Requisite Element", "Status", "Confidence", "Documentary Source Evidence"].forEach((h) => head.append(el("th", h)));
  table.append(el("thead", undefined).appendChild(head));

  const tbody = el("tbody");

  mi.fields.forEach((f) => {
    const row = el("tr");

    // Requisite Item & Importance
    const item = el("td");
    const itemTitle = el("strong", f.label);
    const impBadge = badge(f.importance, f.importance === "required" ? "badge-primary" : "badge-neutral");
    item.append(itemTitle, el("div", undefined, "mt-1").appendChild(impBadge).parentElement);

    // Status
    const status = el("td");
    const statusCls = f.status === "found" ? "badge-success" : f.status === "missing" ? "badge-danger" : "badge-warn";
    status.append(badge(f.status.toUpperCase(), statusCls));

    // Confidence
    const conf = el("td");
    const confCls = f.confidence === "high" ? "badge-success" : f.confidence === "medium" ? "badge-warn" : "badge-neutral";
    conf.append(badge(`${f.confidence} confidence`, confCls));
    if (f.reason) {
      conf.append(el("div", f.reason, "text-xs text-muted mt-1"));
    }

    // Evidence
    const evidence = el("td");
    if (f.status === "missing") {
      const gapTag = el("span", "[information needed in petition]", "badge-gap-marker");
      evidence.append(gapTag);
      if (f.possible_mentions && f.possible_mentions.length) {
        evidence.append(el("div", "Potential candidates discovered in passages:", "text-xs text-muted mt-1"));
        f.possible_mentions.forEach((m) => evidence.append(sourceLine(m.chunk_id, m.text)));
      }
    } else {
      f.sources.forEach((s) => evidence.append(sourceLine(s.chunk_id, s.quote, s.value)));
    }

    row.append(item, status, conf, evidence);
    tbody.append(row);
  });

  table.append(tbody);
  tableWrap.append(table);
  wrap.append(tableWrap);

  if (mi.unverified_extractions && mi.unverified_extractions.length) {
    const unvBox = el("div", undefined, "unverified-alert-box");
    mi.unverified_extractions.forEach((u) => {
      unvBox.append(
        el("p", `Dropped from ${u.doc_id}: Extracted assertions omitted because verbatim quote was absent in record: ${u.keys.join(", ")}`, "text-xs text-muted")
      );
    });
    wrap.append(unvBox);
  }

  return wrap;
}

function renderContradictions(c) {
  const wrap = el("div", undefined, "contradictions-block");

  const head = el("div", undefined, "contradictions-header");
  const countBadge = badge(`${c.items.length} Detected`, c.items.length ? "badge-danger" : "badge-success");
  head.append(el("h4", "Cross-Document Conflict & Contradiction Audit"), countBadge);
  wrap.append(head);

  const sub = el(
    "p",
    `Rigorous cross-record contradiction analysis conducted via ${c.checked_by.join(" + ")}. Potential hallucinations dropped: ${c.dropped_unverified}.`,
    "text-xs text-muted mb-3"
  );
  wrap.append(sub);

  if (c.gemini_error) {
    const warnBox = el("div", undefined, "alert-box alert-warn");
    warnBox.append(el("span", `LLM reasoning offline (Deterministic cross-check executed): ${c.gemini_error}`));
    wrap.append(warnBox);
  }

  if (!c.items.length) {
    const emptyBox = el("div", undefined, "clean-audit-card");
    emptyBox.append(
      icon("check", "icon-success"),
      el("strong", "No factual contradictions detected"),
      el("p", "All extracted dates, identities, sections, and party narratives are mutually consistent across the case filings.", "text-xs text-muted")
    );
    wrap.append(emptyBox);
    return wrap;
  }

  c.items.forEach((it) => {
    const box = el("div", undefined, `conflict-card severity-${it.severity}`);
    const cardTop = el("div", undefined, "conflict-card-top");

    const left = el("div", undefined, "conflict-topic-group");
    const sevBadge = badge(it.severity.toUpperCase(), it.severity === "high" ? "badge-danger" : it.severity === "medium" ? "badge-warn" : "badge-neutral");
    left.append(sevBadge, el("strong", ` ${it.topic} `, "conflict-topic-text"));
    cardTop.append(left);

    const right = el("span", `Scope: ${it.scope} • Detected via: ${it.detected_by}`, "text-xs text-muted");
    cardTop.append(right);
    box.append(cardTop);

    if (it.explanation) {
      box.append(el("p", it.explanation, "conflict-explanation"));
    }

    const sidesContainer = el("div", undefined, "conflict-sides-grid");
    it.sides.forEach((s, idx) => {
      const side = el("div", undefined, "conflict-side-col");
      const sideHead = el("span", `Source Assertion ${idx + 1}`, "conflict-side-badge");
      side.append(sideHead, sourceLine(s.chunk_id, s.quote, s.value));
      sidesContainer.append(side);
    });
    box.append(sidesContainer);

    wrap.append(box);
  });

  return wrap;
}

function renderReport(missing, contradictions) {
  reportEl.replaceChildren();
  if (missing) reportEl.append(renderMissing(missing));
  if (contradictions) reportEl.append(renderContradictions(contradictions));
}

async function loadDraftTypes() {
  try {
    const res = await fetch("/draft-types");
    const types = await res.json();
    draftTypeSel.replaceChildren();
    types.forEach((t) => {
      const opt = el("option", t.label);
      opt.value = t.id;
      draftTypeSel.append(opt);
    });
  } catch (err) {
    console.error("Failed to load draft types:", err);
  }
}

async function refreshReport() {
  try {
    const res = await fetch("/case?full=1");
    const store = await res.json();
    const out = store.outputs || {};
    if (!store.documents.length) {
      reportEl.replaceChildren();
      if (reportStatus) reportStatus.textContent = "Upload case documents to run audit.";
      return;
    }
    if (out.missing_info && out.contradictions) {
      if (out.missing_info.draft_type) draftTypeSel.value = out.missing_info.draft_type;
      renderReport(out.missing_info, out.contradictions);
      if (reportStatus) reportStatus.textContent = `Last examined: ${out.missing_info.analyzed_at}`;
    } else {
      reportEl.replaceChildren();
      if (reportStatus) reportStatus.textContent = "Matter records updated. Click 'Run Case Analysis' to generate audit report.";
    }
  } catch (err) {
    if (reportStatus) reportStatus.textContent = err.message;
  }
}

async function runAnalysis() {
  analyzeBtn.disabled = true;
  if (reportStatus) reportStatus.textContent = "Running automated audit & cross-document verification. This can take 30-60 seconds...";
  toast("Examining case record for contradictions and required elements...", "info", 5000);

  try {
    const res = await fetch("/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ draft_type: draftTypeSel.value }),
    });
    const data = await res.json();
    if (!res.ok) {
      toast(`Analysis error: ${data.error}`, "error", 6000);
      if (reportStatus) reportStatus.textContent = data.error;
      return;
    }
    renderReport(data.missing_info, data.contradictions);
    toast("Case analysis & verification audit complete.", "success");
    if (typeof logActivity === "function") {
      logActivity("Case Analyzed", `Generated readiness report for ${data.missing_info.label}.`, "success");
    }
    if (reportStatus) {
      reportStatus.textContent = data.saved
        ? `Audit completed at ${data.missing_info.analyzed_at}.`
        : "Record updated during analysis. Re-run recommended.";
    }
    document.dispatchEvent(new Event("case-changed"));
  } catch (err) {
    toast(`Analysis error: ${err.message}`, "error");
    if (reportStatus) reportStatus.textContent = err.message;
  } finally {
    analyzeBtn.disabled = false;
  }
}

analyzeBtn.addEventListener("click", runAnalysis);
document.addEventListener("case-changed", refreshReport);
loadDraftTypes().then(refreshReport);
