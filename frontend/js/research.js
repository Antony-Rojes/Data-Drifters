// ============================================================================
// AGENTIC LEGAL ASSISTANT — LEGAL RESEARCH & RETRIEVAL ENGINE
// Real semantic & keyword legal authority search backed by /retrieve
// ============================================================================

const researchInput = document.getElementById("researchInput");
const researchBtn = document.getElementById("researchBtn");
const researchModeSel = document.getElementById("researchMode");
const researchResults = document.getElementById("researchResults");
const researchStatus = document.getElementById("researchStatus");

async function runLegalResearch() {
  const query = (researchInput ? researchInput.value : "").trim();
  if (!query) {
    toast("Please enter a legal query, section, or keyword.", "warn");
    return;
  }

  researchBtn.disabled = true;
  if (researchStatus) researchStatus.textContent = "Retrieving relevant legal authorities and case passages...";
  researchResults.replaceChildren(
    el("div", "Searching indexed records using hybrid retrieval...", "loading-placeholder")
  );

  try {
    const mode = researchModeSel ? researchModeSel.value : "hybrid";
    const res = await fetch("/retrieve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, k: 10, mode }),
    });
    const data = await res.json();
    if (!res.ok) {
      researchResults.replaceChildren(
        el("div", `Research error: ${data.error}`, "alert-box alert-danger")
      );
      if (researchStatus) researchStatus.textContent = data.error;
      return;
    }

    renderResearchResults(query, data);
    if (researchStatus) {
      researchStatus.textContent = `Found ${data.chunks?.length || 0} authority passages via ${data.mode_used || mode} retrieval.`;
    }
    if (typeof logActivity === "function") {
      logActivity("Legal Research Query", `Searched "${query.slice(0, 35)}..." (${data.chunks?.length || 0} results).`, "info");
    }
  } catch (err) {
    researchResults.replaceChildren(
      el("div", `Network error: ${err.message}`, "alert-box alert-danger")
    );
    if (researchStatus) researchStatus.textContent = err.message;
  } finally {
    researchBtn.disabled = false;
  }
}

function renderResearchResults(query, data) {
  researchResults.replaceChildren();
  const chunks = data.chunks || [];

  if (!chunks.length) {
    const emptyBox = el("div", undefined, "empty-state-card");
    emptyBox.append(
      icon("search", "empty-state-icon"),
      el("h4", "No matching legal authorities or case passages found"),
      el("p", `No documents in the current case matched "${query}". Verify search terms or upload additional case filings.`, "text-muted")
    );
    researchResults.append(emptyBox);
    return;
  }

  const header = el("div", undefined, "research-results-summary");
  header.append(
    el("strong", `Identified ${chunks.length} Relevant Evidentiary Citations`),
    el("span", `Ranked by retrieval model: ${data.mode_used || "Hybrid BM25 + Dense"}`, "text-xs text-muted")
  );
  researchResults.append(header);

  chunks.forEach((chunk, idx) => {
    const card = el("article", undefined, "research-result-card");

    const top = el("div", undefined, "result-card-top");
    const rankBadge = el("span", `#${idx + 1}`, "rank-badge");
    const chunkBtn = cidButton(chunk.chunk_id, chunk.text?.slice(0, 100));
    const scorePill = el(
      "span",
      typeof chunk.score === "number" ? `Score: ${chunk.score.toFixed(3)}` : "Ranked",
      "badge-pill badge-primary"
    );

    top.append(rankBadge, chunkBtn, scorePill);
    card.append(top);

    // Text snippet with matching query words highlighted
    const passage = el("div", undefined, "result-passage-body");
    passage.textContent = chunk.text;
    card.append(passage);

    const bottom = el("div", undefined, "result-card-bottom");
    const inspectBtn = el("button", "Inspect in Source Drawer", "btn btn-ghost btn-sm");
    inspectBtn.prepend(icon("externalLink"));
    inspectBtn.addEventListener("click", () => showSource(chunk.chunk_id, "", inspectBtn));

    bottom.append(
      el("span", `Passage ID: ${chunk.chunk_id}`, "text-xs text-muted"),
      inspectBtn
    );
    card.append(bottom);

    researchResults.append(card);
  });
}

if (researchBtn) {
  researchBtn.addEventListener("click", runLegalResearch);
}
if (researchInput) {
  researchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") runLegalResearch();
  });
}
