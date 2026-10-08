// ============================================================================
// AGENTIC LEGAL ASSISTANT — DOCUMENT MANAGEMENT & EXTRACTION
// Drag-and-drop upload, OCR transparency, structured fact explorer
// ============================================================================

const fileInput = document.getElementById("fileInput");
const uploadBtn = document.getElementById("uploadBtn");
const resetBtn = document.getElementById("resetBtn");
const statusEl = document.getElementById("status");
const docsEl = document.getElementById("docs");
const dropzone = document.getElementById("dropzone");

function renderDocs(documents) {
  docsEl.replaceChildren();
  const badgeCount = document.getElementById("navDocCount");
  if (badgeCount) badgeCount.textContent = String(documents.length);

  if (!documents.length) {
    const emptyState = el("div", undefined, "empty-state-card");
    emptyState.append(
      icon("document", "empty-state-icon"),
      el("h4", "No case documents uploaded yet"),
      el("p", "Upload judicial filings, FIRs, witness testimonies, or police chargesheets in PDF format to begin automated analysis and citation extraction.", "muted"),
      el("button", "Browse PDF Files", "btn btn-primary")
    );
    emptyState.querySelector("button").addEventListener("click", () => fileInput.click());
    docsEl.append(emptyState);
    return;
  }

  // Document management table
  const tableWrap = el("div", undefined, "table-responsive");
  const table = el("table", undefined, "legal-table");
  const thead = el("thead");
  const headRow = el("tr");
  ["Record ID", "Document Title", "Classification", "Pages", "Passages", "Verified Facts", "Actions"].forEach((h) => {
    headRow.append(el("th", h));
  });
  thead.append(headRow);
  table.append(thead);

  const tbody = el("tbody");

  documents.forEach((doc) => {
    const row = el("tr");
    
    // Doc ID
    const tdId = el("td");
    tdId.append(el("span", doc.doc_id, "badge-doc-id"));

    // Title
    const tdName = el("td");
    const nameWrap = el("div", undefined, "doc-title-cell");
    nameWrap.append(icon("document", "doc-icon-subtle"), el("strong", doc.filename));
    if (doc.ocr_pages && doc.ocr_pages.length) {
      const ocrPill = el("span", `OCR: pp. ${doc.ocr_pages.join(", ")}`, "badge-pill badge-warn");
      ocrPill.title = "Scanned optical character recognition was performed on these pages";
      nameWrap.append(ocrPill);
    }
    tdName.append(nameWrap);

    // Classification
    const tdType = el("td");
    tdType.append(el("span", doc.document_type || "Court Filing", "badge-pill badge-neutral"));

    // Pages & Chunks
    const tdPages = el("td", `${doc.page_count} pp.`);
    const tdChunks = el("td", `${doc.chunk_count} passages`);

    // Facts Count
    const factCount = Object.keys(doc.facts || {}).length;
    const tdFacts = el("td");
    tdFacts.append(el("span", `${factCount} extracted`, factCount ? "text-success font-semibold" : "muted"));

    // Actions
    const tdActions = el("td");
    const actionGroup = el("div", undefined, "action-btn-group");

    // PDF link
    const viewPdfBtn = el("a", "Open PDF", "btn btn-ghost btn-sm");
    viewPdfBtn.href = `/pdf/${encodeURIComponent(doc.doc_id)}`;
    viewPdfBtn.target = "_blank";
    viewPdfBtn.rel = "noopener";
    viewPdfBtn.prepend(icon("externalLink"));

    // Inspect Facts Toggle
    const inspectBtn = el("button", "Inspect Facts", "btn btn-secondary btn-sm");
    inspectBtn.type = "button";

    actionGroup.append(viewPdfBtn, inspectBtn);
    tdActions.append(actionGroup);

    row.append(tdId, tdName, tdType, tdPages, tdChunks, tdFacts, tdActions);
    tbody.append(row);

    // Expandable Fact Inspector Row
    const factRow = el("tr", undefined, "fact-inspector-row");
    factRow.hidden = true;
    const factTd = el("td");
    factTd.colSpan = 7;

    const factBox = el("div", undefined, "fact-inspector-box");
    const factHead = el("div", undefined, "fact-inspector-header");
    factHead.append(
      el("h5", `Extracted Evidentiary Facts: ${doc.filename}`),
      el("span", `${factCount} key points grounded in text`, "muted")
    );
    factBox.append(factHead);

    if (factCount > 0) {
      const factTableWrap = el("div", undefined, "table-responsive");
      const factTable = el("table", undefined, "legal-table fact-inner-table");
      const fHead = el("tr");
      ["Legal Attribute", "Extracted Value", "Verifiable Evidence Quote"].forEach((h) => fHead.append(el("th", h)));
      factTable.append(el("thead", undefined).appendChild(fHead));

      const fBody = el("tbody");
      Object.entries(doc.facts).forEach(([key, fact]) => {
        const fr = el("tr");
        const kTd = el("td");
        kTd.append(el("code", key, "fact-key-tag"));
        const vTd = el("td", fact.value, "fact-val-text");
        const sTd = el("td");
        sTd.append(cidButton(fact.chunk_id, fact.quote));
        fr.append(kTd, vTd, sTd);
        fBody.append(fr);
      });
      factTable.append(fBody);
      factTableWrap.append(factTable);
      factBox.append(factTableWrap);
    } else {
      factBox.append(el("p", "No structured key-value facts identified in this document.", "muted"));
    }

    if (doc.unverified_facts && doc.unverified_facts.length) {
      const dropNotice = el("div", undefined, "dropped-facts-alert");
      dropNotice.append(
        icon("alertTriangle", "icon-warn"),
        el("span", `Discarded ${doc.unverified_facts.length} unverified assertion(s) (verbatim quote absent in source text): ${doc.unverified_facts.join(", ")}`)
      );
      factBox.append(dropNotice);
    }

    factTd.append(factBox);
    factRow.append(factTd);
    tbody.append(factRow);

    inspectBtn.addEventListener("click", () => {
      factRow.hidden = !factRow.hidden;
      inspectBtn.textContent = factRow.hidden ? "Inspect Facts" : "Hide Facts";
    });
  });

  table.append(tbody);
  tableWrap.append(table);
  docsEl.append(tableWrap);
}

async function loadCase() {
  try {
    const res = await fetch("/case");
    const data = await res.json();
    renderDocs(data.documents);
    const caseChip = document.getElementById("caseChip");
    if (caseChip) {
      caseChip.textContent = data.case_id ? `Matter: ${data.case_id}` : "No active matter";
    }
    document.dispatchEvent(new CustomEvent("case-changed", { detail: { caseId: data.case_id } }));
  } catch (err) {
    if (statusEl) statusEl.textContent = `Failed to load case: ${err.message}`;
  }
}

async function uploadFiles(filesList) {
  const files = filesList || [...fileInput.files];
  if (!files.length) {
    toast("Please choose at least one PDF file to upload.", "warn");
    return;
  }
  uploadBtn.disabled = true;
  if (dropzone) dropzone.classList.add("is-uploading");

  for (const file of files) {
    if (statusEl) statusEl.textContent = `Processing and extracting facts from ${file.name}...`;
    toast(`Ingesting and performing OCR on ${file.name}...`, "info", 4000);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch("/upload", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) {
        toast(`${file.name}: ${data.error}`, "error", 6000);
        if (statusEl) statusEl.textContent = `${file.name}: ${data.error}`;
        break;
      }
      if (data.duplicate) {
        toast(data.message, "warn");
      } else {
        toast(`Successfully added ${file.name} to case record.`, "success");
        if (typeof logActivity === "function") {
          logActivity("Document Uploaded", `${file.name} processed and indexed with citation chunks.`, "success");
        }
      }
      if (statusEl) statusEl.textContent = data.duplicate ? data.message : `${file.name} added.`;
    } catch (err) {
      toast(`${file.name} upload error: ${err.message}`, "error");
      if (statusEl) statusEl.textContent = `${file.name}: ${err.message}`;
      break;
    }
  }
  fileInput.value = "";
  uploadBtn.disabled = false;
  if (dropzone) dropzone.classList.remove("is-uploading");
  await loadCase();
}

async function resetCase() {
  if (!confirm("Are you sure you want to begin a New Case? The current matter documents will be archived safely.")) return;
  try {
    await fetch("/reset", { method: "POST" });
    toast("Previous matter archived. New case initialized.", "info");
    if (statusEl) statusEl.textContent = "New case matter initialized.";
    if (typeof logActivity === "function") {
      logActivity("Case Archived", "Started fresh matter workspace.", "info");
    }
    await loadCase();
  } catch (err) {
    toast(`Reset error: ${err.message}`, "error");
  }
}

// Drag & Drop Setup
if (dropzone) {
  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("is-dragover");
  });
  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("is-dragover");
  });
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("is-dragover");
    if (e.dataTransfer && e.dataTransfer.files.length) {
      uploadFiles([...e.dataTransfer.files]);
    }
  });
}

uploadBtn.addEventListener("click", () => uploadFiles());
resetBtn.addEventListener("click", resetCase);
loadCase();
