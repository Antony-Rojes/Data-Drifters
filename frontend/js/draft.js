// ============================================================================
// AGENTIC LEGAL ASSISTANT — AUTOMATED PETITION DRAFTING STUDIO
// Verifiable legal drafting with zero-fabrication citations & court-paper styling
// ============================================================================

const draftKind = document.getElementById("draftKind");
const draftBtn = document.getElementById("draftBtn");
const draftInstructions = document.getElementById("draftInstructions");
const draftStatus = document.getElementById("draftStatus");
const draftOut = document.getElementById("draftOut");

function renderDraft(d) {
  draftOut.replaceChildren();

  // 1. Audit & Verification Gauge Header
  draftOut.append(validationChecks(d.validation));

  // 2. Metadata Strip
  const metaStrip = el("div", undefined, "draft-meta-strip");
  const metaText = [`Generated ${d.generated_at} from ${d.doc_ids.join(", ")}.`, `Retrieval mode: ${d.retrieval.mode_used}.`];
  if (d.source === "backup_template") metaText.push("Gemini offline; assembled from verified extraction facts.");
  metaStrip.append(el("span", metaText.join(" "), "text-xs text-muted"));

  if (d.readiness) {
    const rBadge = el("span", `${d.readiness.required_found}/${d.readiness.required_total} Elements Satisfied`, "badge-pill badge-neutral");
    metaStrip.append(rBadge);
  }
  draftOut.append(metaStrip);

  if (d.notes && d.notes.length) {
    const notesBox = el("div", undefined, "draft-notes-box");
    d.notes.forEach((n) => notesBox.append(el("p", n, "text-xs text-warn")));
    draftOut.append(notesBox);
  }

  // 3. Courtroom Legal Paper Presentation
  const paper = el("article", undefined, "legal-court-paper");

  // Court Title
  const paperHeader = el("div", undefined, "court-paper-heading");
  paperHeader.append(el("h3", d.title.toUpperCase(), "court-paper-title"));
  paper.append(paperHeader);

  const refs = [];
  d.sections.forEach((sec) => {
    if (!sec.sentences.length) return;
    const secWrap = el("div", undefined, "paper-section");
    secWrap.append(el("h4", sec.heading, "paper-section-heading"));
    secWrap.append(sentencesParagraph(sec.sentences, refs));
    paper.append(secWrap);
  });

  if (refs.length) {
    const srcSec = el("div", undefined, "paper-section paper-sources-section");
    srcSec.append(el("h4", "SCHEDULE OF EVIDENCE & DOCUMENTARY CITATIONS", "paper-section-heading"));
    srcSec.append(sourcesList(refs));
    paper.append(srcSec);
  }
  draftOut.append(paper);

  // 4. Action Toolbar
  const actionRow = el("div", undefined, "draft-actions-toolbar");
  const leftActions = el("div", undefined, "action-btn-group");

  const dlBtn = el("a", "Download Filing (.txt)", "btn btn-primary btn-sm");
  dlBtn.href = `/draft/${encodeURIComponent(d.draft_type)}.txt`;
  dlBtn.prepend(icon("download"));

  const printBtn = el("button", "Print Formal Filing", "btn btn-secondary btn-sm");
  printBtn.type = "button";
  printBtn.prepend(icon("printer"));
  printBtn.addEventListener("click", () => {
    const card = draftOut.closest(".card") || draftOut;
    card.classList.add("print-active-filing");
    window.print();
    card.classList.remove("print-active-filing");
  });

  const copyBtn = el("button", "Copy Plain Text", "btn btn-secondary btn-sm");
  copyBtn.type = "button";
  copyBtn.prepend(icon("copy"));
  copyBtn.addEventListener("click", () => {
    const textToCopy = paper.innerText;
    navigator.clipboard.writeText(textToCopy).then(() => {
      toast("Draft text copied to clipboard.", "success");
    });
  });

  leftActions.append(dlBtn, printBtn, copyBtn);
  actionRow.append(leftActions);
  draftOut.append(actionRow);

  // 5. Audit Log of Removed / Replaced Items
  if (d.removed && d.removed.length) {
    const auditDrawer = el("details", undefined, "audit-removed-drawer");
    auditDrawer.append(
      el("summary", `Validator Pruning Audit: ${d.removed.length} assertion(s) withheld from filing to prevent hallucination`)
    );

    const auditList = el("div", undefined, "audit-removed-list");
    d.removed.forEach((r) => {
      const item = el("div", undefined, "audit-removed-item");
      const quoteS = el("s", `"${r.original_text}"`, "audit-removed-quote");
      const reasonBadge = el("div", `${r.section ? `[${r.section}] ` : ""}${r.reason}`, "badge-pill badge-danger mt-1");
      item.append(quoteS, reasonBadge);
      auditList.append(item);
    });
    auditDrawer.append(auditList);
    draftOut.append(auditDrawer);
  }
}

async function loadDraftKinds() {
  try {
    const res = await fetch("/draft-types");
    const types = await res.json();
    draftKind.replaceChildren();
    types.forEach((t) => {
      const opt = el("option", t.label);
      opt.value = t.id;
      draftKind.append(opt);
    });
  } catch (err) {
    console.error("Failed to load draft kinds:", err);
  }
}

async function refreshDraft() {
  try {
    const res = await fetch("/case?full=1");
    const store = await res.json();
    const saved = ((store.outputs || {}).drafts || {})[draftKind.value];
    if (saved) {
      renderDraft(saved);
      if (draftStatus) draftStatus.textContent = "Displaying verified courtroom draft from current matter.";
    } else {
      draftOut.replaceChildren();
      if (draftStatus) {
        draftStatus.textContent = store.documents.length
          ? "No draft generated yet for this draft type. Click 'Generate Court Draft' to synthesize."
          : "Upload case record documents before generating pleadings.";
      }
    }
  } catch (err) {
    if (draftStatus) draftStatus.textContent = err.message;
  }
}

async function generateDraft() {
  draftBtn.disabled = true;
  if (draftStatus) draftStatus.textContent = "Synthesizing legal pleading and auditing citations through Feature 4. Please wait 30-60s...";
  toast("Generating structured draft and running deterministic citation audit...", "info", 5000);

  try {
    const res = await fetch("/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ draft_type: draftKind.value, instructions: draftInstructions.value }),
    });
    const data = await res.json();
    if (!res.ok) {
      toast(`Drafting failed: ${data.error}`, "error", 6000);
      if (draftStatus) draftStatus.textContent = data.error;
      return;
    }
    renderDraft(data);
    toast("Court pleading drafted and citation audited.", "success");
    if (typeof logActivity === "function") {
      logActivity("Pleading Generated", `Generated verified draft for ${draftKind.options[draftKind.selectedIndex]?.text || draftKind.value}.`, "success");
    }
    if (draftStatus) {
      draftStatus.textContent = data.saved ? "Court filing draft prepared and verified." : "Record modified during drafting. Please regenerate.";
    }
    document.dispatchEvent(new Event("case-changed"));
  } catch (err) {
    toast(`Drafting error: ${err.message}`, "error");
    if (draftStatus) draftStatus.textContent = err.message;
  } finally {
    draftBtn.disabled = false;
  }
}

draftBtn.addEventListener("click", generateDraft);
draftKind.addEventListener("change", refreshDraft);
document.addEventListener("case-changed", refreshDraft);
loadDraftKinds().then(refreshDraft);
