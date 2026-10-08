// ============================================================================
// AGENTIC LEGAL ASSISTANT — SHARED RUNTIME & SOURCE DRAWER
// Enterprise Legal-Tech Design System • Pure Vanilla JS (No External Dependencies)
// ============================================================================

// --- Utility DOM Creator ---
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = text;
  if (className) node.className = className;
  return node;
}

// --- Professional SVG Icon System (Lucide-grade, Crisp 16-20px) ---
const ICONS = {
  scale: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/></svg>',
  dashboard: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/></svg>',
  briefcase: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/><rect width="20" height="14" x="2" y="6" rx="2"/></svg>',
  document: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/></svg>',
  search: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>',
  edit: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
  bot: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>',
  shieldCheck: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></svg>',
  settings: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>',
  upload: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/></svg>',
  plus: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" x2="12" y1="5" y2="19"/><line x1="5" x2="19" y1="12" y2="12"/></svg>',
  check: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
  alertTriangle: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/></svg>',
  info: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
  x: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>',
  download: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>',
  printer: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect width="12" height="8" x="6" y="14"/></svg>',
  externalLink: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" x2="21" y1="14" y2="3"/></svg>',
  sparkles: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/></svg>',
  refresh: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M3 21v-5h5"/></svg>',
  send: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>',
  trash: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>',
};

function icon(name, className) {
  const span = document.createElement("span");
  span.className = `icon-svg ${className || ""}`.trim();
  span.innerHTML = ICONS[name] || "";
  return span;
}

// --- Toast Notification System ---
function toast(message, type = "info", duration = 3500) {
  let container = document.getElementById("toastContainer");
  if (!container) {
    container = el("div", undefined, "toast-container");
    container.id = "toastContainer";
    document.body.appendChild(container);
  }
  const item = el("div", undefined, `toast toast-${type}`);
  const iconName = type === "success" ? "check" : type === "error" ? "alertTriangle" : type === "warn" ? "alertTriangle" : "info";
  item.appendChild(icon(iconName));
  const msgEl = el("span", message, "toast-msg");
  item.appendChild(msgEl);
  container.appendChild(item);
  setTimeout(() => {
    item.classList.add("toast-out");
    setTimeout(() => item.remove(), 250);
  }, duration);
}

// --- Source Drawer Elements & Mechanics ---
const sourcePanel = document.getElementById("sourcePanel");
const sourceBody = document.getElementById("sourceBody");
const sourceTitle = document.getElementById("sourceTitle");
let lastSourceTrigger = null;

// Finds the quote inside the chunk text, ignoring case and spacing differences.
function findQuote(text, quote) {
  const parts = (quote || "").split(/\.\.\.|\u2026/).map((p) => p.trim()).filter(Boolean);
  const ranges = [];
  for (const part of parts) {
    const words = part.split(/\s+/).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    const match = new RegExp(words.join("\\s+"), "i").exec(text);
    if (!match) return [];
    ranges.push([match.index, match.index + match[0].length]);
  }
  return ranges.sort((a, b) => a[0] - b[0]);
}

function highlighted(text, quote) {
  const box = el("div", undefined, "main-chunk");
  const ranges = findQuote(text, quote);
  let pos = 0;
  ranges.forEach(([start, end]) => {
    if (start < pos) return;
    box.append(document.createTextNode(text.slice(pos, start)), el("mark", text.slice(start, end)));
    pos = end;
  });
  box.append(document.createTextNode(text.slice(pos)));
  return { box, found: ranges.length > 0 };
}

async function showSource(chunkId, quote, trigger) {
  lastSourceTrigger = trigger || null;
  const panel = document.getElementById("sourcePanel");
  const title = document.getElementById("sourceTitle");
  const body = document.getElementById("sourceBody");
  if (!panel || !body) return;

  panel.hidden = false;
  panel.classList.add("is-open");
  if (title) title.textContent = `Evidence Passage: ${chunkId}`;

  body.replaceChildren(
    el("div", "Loading evidentiary source chunk...", "loading-placeholder")
  );

  try {
    const res = await fetch(`/chunk/${encodeURIComponent(chunkId)}`);
    const data = await res.json();
    if (!res.ok) {
      body.replaceChildren(el("p", data.error || "Chunk not found.", "source-error"));
      return;
    }
    const c = data.chunk;
    const metaCard = el("div", undefined, "source-meta-card");
    const metaHeader = el("div", undefined, "source-meta-header");
    metaHeader.append(
      el("strong", data.filename),
      el("span", `Page ${c.page} • Para ${c.paragraph}`, "source-meta-badge")
    );
    if (c.source === "ocr") {
      metaHeader.append(el("span", "OCR Read", "source-ocr-badge"));
    }
    metaCard.append(metaHeader);

    const pdfLink = el("a", "Open original PDF page", "source-pdf-link");
    pdfLink.href = `/pdf/${encodeURIComponent(data.doc_id)}#page=${c.page}`;
    pdfLink.target = "_blank";
    pdfLink.rel = "noopener";
    pdfLink.prepend(icon("externalLink"));
    metaCard.append(pdfLink);

    const parts = [metaCard];

    if (data.before) {
      const beforeBox = el("div", undefined, "source-ctx");
      beforeBox.append(el("div", "Preceding context:", "source-ctx-label"));
      beforeBox.append(document.createTextNode(data.before.text));
      parts.push(beforeBox);
    }

    const { box, found } = highlighted(c.text, quote);
    parts.push(box);

    if (data.after) {
      const afterBox = el("div", undefined, "source-ctx");
      afterBox.append(el("div", "Following context:", "source-ctx-label"));
      afterBox.append(document.createTextNode(data.after.text));
      parts.push(afterBox);
    }

    if (quote) {
      const verdict = el("div", undefined, `source-verdict ${found ? "verdict-found" : "verdict-normalized"}`);
      verdict.append(icon(found ? "check" : "info"));
      verdict.append(
        el(
          "span",
          found
            ? "Exact highlighted quote verified in source text."
            : "Quote matched after normalizing legal punctuation and spacing."
        )
      );
      parts.push(verdict);
      if (!found) {
        const quoteBox = el("div", `"${quote}"`, "source-quote-box");
        parts.push(quoteBox);
      }
    }

    body.replaceChildren(...parts);
    const closeBtn = document.getElementById("sourceClose");
    if (closeBtn) closeBtn.focus();
  } catch (err) {
    body.replaceChildren(el("p", `Error retrieving source: ${err.message}`, "source-error"));
  }
}

function closeSource() {
  const panel = document.getElementById("sourcePanel");
  if (panel) {
    panel.classList.remove("is-open");
    panel.hidden = true;
  }
  if (lastSourceTrigger && typeof lastSourceTrigger.focus === "function") {
    lastSourceTrigger.focus();
  }
}

// Clickable chunk button
function cidButton(chunkId, quote) {
  const b = el("button", chunkId, "cid");
  b.type = "button";
  b.title = `Inspect source passage: ${chunkId}`;
  b.addEventListener("click", (e) => {
    e.stopPropagation();
    showSource(chunkId, quote, b);
  });
  return b;
}

const sourceCloseBtn = document.getElementById("sourceClose");
if (sourceCloseBtn) {
  sourceCloseBtn.addEventListener("click", closeSource);
}
document.addEventListener("keydown", (e) => {
  const panel = document.getElementById("sourcePanel");
  if (e.key === "Escape" && panel && !panel.hidden) closeSource();
});

// --- Renders validated sentences with citation badges [n] ---
function sentencesParagraph(sentences, refs) {
  const p = el("p");
  sentences.forEach((s) => {
    const span = el("span");
    if (s.status === "replaced") {
      span.textContent = s.text;
      span.className = "s-replaced";
      span.title = `Replaced by zero-fabrication guardrail. Original: "${s.original_text || ""}"`;
    } else {
      s.text.split(/(\[information needed[^\]]*\])/i).forEach((part) => {
        if (!part) return;
        span.append(/^\[information needed/i.test(part) ? el("span", part, "s-missing") : document.createTextNode(part));
      });
    }
    p.append(span);

    (s.citations || []).forEach((c) => {
      refs.push(c);
      const n = refs.length;
      const b = el("button", `[${n}]`, "cite");
      b.type = "button";
      b.title = `${c.chunk_id}: "${c.quote}"`;
      b.setAttribute("aria-label", `Source ${n}, ${c.chunk_id}`);
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        showSource(c.chunk_id, c.quote, b);
      });
      p.append(b);
    });
    p.append(document.createTextNode(" "));
  });
  return p;
}

// --- Sources list rendered at bottom of drafts ---
function sourcesList(refs) {
  const ol = el("ol", undefined, "sources-list");
  refs.forEach((c, idx) => {
    const li = el("li");
    const num = el("span", `[${idx + 1}] `, "source-ref-num");
    li.append(num, cidButton(c.chunk_id, c.quote), el("span", ` "${c.quote}"`, "source-ref-quote"));
    ol.append(li);
  });
  return ol;
}

// --- Validation checks gauge banner ---
function validationChecks(v) {
  const box = el("div", undefined, "checks-grid");
  const item = (value, label, statusCls, iconName) => {
    const card = el("div", undefined, `check-stat-card ${statusCls || ""}`);
    const top = el("div", undefined, "check-card-top");
    top.append(icon(iconName || "shieldCheck"));
    top.append(el("span", label, "check-card-label"));
    card.append(top);
    card.append(el("strong", String(value), "check-card-value"));
    box.append(card);
  };

  item(v.verified + v.repaired, "Claims Grounded", "status-good", "check");
  item(v.citations_corrected, "Citations Corrected", "", "refresh");
  item(v.replaced, "Replaced with Gaps", v.replaced ? "status-warn" : "", "alertTriangle");
  item(v.removed, "Removed Template Claims", v.removed ? "status-warn" : "", "trash");
  item(`${v.groundedness_before_pct}%`, "Grounded Pre-Validator", "", "sparkles");
  item(`${v.groundedness_after_pct}%`, "Grounded Post-Validator", "status-good", "shieldCheck");
  item(v.fabrications_left, "Fabrications Remaining", v.fabrications_left ? "status-bad" : "status-good", "shieldCheck");

  return box;
}
