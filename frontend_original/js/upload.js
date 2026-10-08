(() => {
  "use strict";

  const MAX_MB = 25;

  const state = {
    store: null,          // full store.json from the backend
    queue: [],            // upload queue items
    processing: false,
    openDocs: new Set(),  // doc_ids whose card is expanded
    seenDocs: new Set(),
    filter: "",
    missingOnly: false,
    lastFocus: null,
    nextId: 1,
  };

  const $ = (id) => document.getElementById(id);

  // ---------- helpers ----------
  // Builds elements with textContent only, so text from PDFs can never run as HTML.
  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (value === undefined || value === null || value === false) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child);
    }
    return node;
  }

  async function api(path, options) {
    const res = await fetch(path, options);
    let data = null;
    try { data = await res.json(); } catch (_) { /* no JSON body */ }
    if (!res.ok) throw new Error((data && data.error) || `Request failed (${res.status})`);
    return data;
  }

  function toast(message, type = "info") {
    const node = el("div", { class: `toast toast-${type}`, role: type === "error" ? "alert" : "status", text: message });
    $("toasts").append(node);
    setTimeout(() => {
      node.classList.add("is-leaving");
      setTimeout(() => node.remove(), 260);
    }, type === "error" ? 7000 : 3500);
  }

  const isMissing = (value) =>
    value === null || value === undefined || /^(blank|)$/i.test(String(value).trim());

  function prettyKey(key) {
    const text = String(key).replace(/_/g, " ").trim();
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  function formatSize(bytes) {
    if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  const escapeRegex = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  // ---------- loading ----------
  async function loadCase() {
    try {
      state.store = await api("/case?full=1");
    } catch (err) {
      toast(`Could not load the case: ${err.message}`, "error");
      state.store = state.store || { documents: [] };
    }
    render();
  }

  // ---------- rendering ----------
  function render() {
    const docs = (state.store && state.store.documents) || [];
    $("caseChip").textContent = (state.store && state.store.case_id) || "No case";
    $("downloadBtn").disabled = docs.length === 0;
    renderStats(docs);
    renderDocs(docs);
  }

  function renderStats(docs) {
    let pages = 0, chunks = 0, facts = 0, missing = 0;
    docs.forEach((doc) => {
      pages += doc.page_count || 0;
      chunks += (doc.chunks || []).length;
      Object.values(doc.facts || {}).forEach((fact) => {
        facts += 1;
        if (isMissing(fact.value)) missing += 1;
      });
    });
    $("statDocs").textContent = docs.length;
    $("statPages").textContent = pages;
    $("statChunks").textContent = chunks;
    $("statFacts").textContent = facts;
    $("statMissing").textContent = missing;
  }

  function renderDocs(docs) {
    const box = $("docs");
    box.replaceChildren();
    $("docCount").textContent = docs.length ? String(docs.length) : "";
    $("filterBar").hidden = docs.length === 0;

    if (!docs.length) {
      box.append(el("div", { class: "empty" },
        el("strong", { text: "No documents yet" }),
        "Upload a PDF above to extract its facts."));
      return;
    }

    // The newest document opens by default; the user's own open/close choices are kept.
    const newest = docs[docs.length - 1];
    docs.forEach((doc) => {
      if (!state.seenDocs.has(doc.doc_id)) {
        state.seenDocs.add(doc.doc_id);
        if (doc === newest) state.openDocs.add(doc.doc_id);
      }
    });

    [...docs].reverse().forEach((doc) => box.append(docCard(doc)));
  }

  function docCard(doc) {
    const entries = Object.entries(doc.facts || {});
    const missingCount = entries.filter(([, fact]) => isMissing(fact.value)).length;
    const unverified = (doc.unverified_facts || []).length;
    const ocrPages = doc.ocr_pages || [];

    const details = el("details", {
      class: "doc",
      open: state.openDocs.has(doc.doc_id),
      ontoggle: (event) => {
        if (event.currentTarget.open) state.openDocs.add(doc.doc_id);
        else state.openDocs.delete(doc.doc_id);
      },
    });

    const badges = el("div", { class: "doc-badges" },
      el("span", { class: "badge badge-info", text: doc.document_type || "document" }),
      ocrPages.length ? el("span", { class: "badge badge-warn", text: "OCR used" }) : null,
      missingCount ? el("span", { class: "badge badge-warn", text: `${missingCount} missing` }) : null,
      !missingCount && entries.length ? el("span", { class: "badge badge-ok", text: "Complete" }) : null,
    );

    details.append(el("summary", { class: "doc-head" },
      el("span", { class: "doc-icon", text: "PDF" }),
      el("div", { class: "doc-title" },
        el("div", { class: "doc-name", text: doc.filename }),
        el("div", { class: "doc-meta",
          text: `${doc.doc_id} · ${doc.page_count} page${doc.page_count === 1 ? "" : "s"} · ${(doc.chunks || []).length} chunks · ${entries.length} facts` }),
      ),
      badges,
    ));

    const body = el("div", { class: "doc-body" });

    body.append(el("div", { class: "doc-tools" },
      el("span", { class: "muted", text: "Click a source ID to see the original text." }),
      el("button", {
        class: "btn btn-ghost btn-small", type: "button", text: "View full text",
        onclick: (event) => openDrawer(doc.doc_id, null, null, event.currentTarget),
      }),
    ));

    if (ocrPages.length) {
      body.append(el("div", { class: "notice", text: `Scanned pages read with OCR: ${ocrPages.join(", ")}. Please check this text.` }));
    }
    if (unverified) {
      body.append(el("div", { class: "notice",
        text: `${unverified} extracted fact${unverified === 1 ? " was" : "s were"} dropped because the quote was not found in the source: ${doc.unverified_facts.join(", ")}` }));
    }

    body.append(factsTable(doc, entries));
    details.append(body);
    return details;
  }

  function factsTable(doc, entries) {
    if (!entries.length) {
      return el("p", { class: "muted", text: "No verified facts were found in this document." });
    }

    const query = state.filter.trim().toLowerCase();
    const rows = entries.filter(([key, fact]) => {
      if (state.missingOnly && !isMissing(fact.value)) return false;
      if (!query) return true;
      return key.toLowerCase().includes(query) || String(fact.value).toLowerCase().includes(query);
    });

    if (!rows.length) {
      return el("p", { class: "muted", text: "No fields match the current filter." });
    }

    const tbody = el("tbody");
    rows.forEach(([key, fact]) => {
      const missing = isMissing(fact.value);
      const source = fact.chunk_id
        ? el("button", {
            class: "chip", type: "button", text: fact.chunk_id,
            title: fact.quote ? `"${fact.quote}"` : "Open source",
            onclick: (event) => openDrawer(doc.doc_id, fact.chunk_id, fact.quote, event.currentTarget),
          })
        : "—";
      tbody.append(el("tr", { class: missing ? "is-missing" : null },
        el("td", { class: "k", title: key, text: prettyKey(key) }),
        el("td", { class: "v" }, missing ? el("span", { class: "badge badge-warn", text: "Missing" }) : String(fact.value)),
        el("td", {}, source),
      ));
    });

    return el("div", { class: "table-wrap" },
      el("table", {},
        el("thead", {}, el("tr", {}, el("th", { text: "Field" }), el("th", { text: "Value" }), el("th", { text: "Source" }))),
        tbody));
  }

  // ---------- source drawer ----------
  function fillHighlighted(node, text, quote) {
    const tokens = quote.trim().split(/\s+/).filter(Boolean).map(escapeRegex);
    const match = tokens.length ? new RegExp(tokens.join("\\s+"), "i").exec(text) : null;
    if (!match) {
      node.textContent = text;
      return;
    }
    node.append(
      text.slice(0, match.index),
      el("mark", { text: match[0] }),
      text.slice(match.index + match[0].length),
    );
  }

  function openDrawer(docId, chunkId, quote, opener) {
    const doc = ((state.store && state.store.documents) || []).find((d) => d.doc_id === docId);
    if (!doc) return;

    state.lastFocus = opener || document.activeElement;
    $("drawerTitle").textContent = doc.filename;
    $("drawerSub").textContent = `${doc.doc_id} · ${doc.page_count} page(s) · ${(doc.chunks || []).length} chunks`;

    const body = $("drawerBody");
    body.replaceChildren();
    let target = null;

    (doc.chunks || []).forEach((chunk) => {
      const isTarget = chunk.chunk_id === chunkId;
      const text = el("p", { class: "chunk-text" });
      if (isTarget && quote) fillHighlighted(text, chunk.text, quote);
      else text.textContent = chunk.text;

      const card = el("article", { class: isTarget ? "chunk is-target" : "chunk" },
        el("header", { class: "chunk-head" },
          el("code", { text: chunk.chunk_id }),
          el("span", { class: "muted", text: `Page ${chunk.page}` }),
          chunk.source === "ocr" ? el("span", { class: "badge badge-warn", text: "OCR" }) : null),
        text);
      if (isTarget) target = card;
      body.append(card);
    });

    $("drawer").classList.add("is-open");
    $("drawer").setAttribute("aria-hidden", "false");
    $("overlay").hidden = false;
    document.body.classList.add("no-scroll");
    $("drawerClose").focus();
    if (target) requestAnimationFrame(() => target.scrollIntoView({ block: "center" }));
    else body.scrollTop = 0;
  }

  function closeDrawer() {
    $("drawer").classList.remove("is-open");
    $("drawer").setAttribute("aria-hidden", "true");
    $("overlay").hidden = true;
    document.body.classList.remove("no-scroll");
    if (state.lastFocus && document.contains(state.lastFocus)) state.lastFocus.focus();
  }

  // ---------- upload queue ----------
  function addFiles(fileList) {
    const files = Array.from(fileList);
    let added = 0;

    files.forEach((file) => {
      const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
      if (!isPdf) {
        toast(`${file.name} is not a PDF.`, "error");
        return;
      }
      if (file.size > MAX_MB * 1024 * 1024) {
        toast(`${file.name} is larger than ${MAX_MB} MB.`, "error");
        return;
      }
      const twin = state.queue.find((q) =>
        q.file.name === file.name && q.file.size === file.size &&
        q.file.lastModified === file.lastModified && q.status !== "error");
      if (twin) {
        toast(`${file.name} is already in the queue.`, "info");
        return;
      }
      state.queue.push({ id: state.nextId++, file, status: "waiting", message: "", elapsed: 0 });
      added += 1;
    });

    if (added) {
      renderQueue();
      processQueue();
    }
  }

  function statusText(item) {
    switch (item.status) {
      case "waiting": return "Waiting";
      case "reading":
        return item.elapsed > 20
          ? `Reading... ${item.elapsed}s (Gemini can be slow when busy)`
          : `Reading... ${item.elapsed}s`;
      case "done": return `Added · ${item.message}`;
      case "duplicate": return item.message || "Already uploaded";
      case "error": return item.message || "Failed";
      default: return "";
    }
  }

  const STATUS_ICON = { waiting: "•", reading: "", done: "✓", duplicate: "=", error: "!" };

  function renderQueue() {
    const list = $("queue");
    list.replaceChildren();
    $("queueWrap").hidden = state.queue.length === 0;

    state.queue.forEach((item) => {
      const actions = el("div", { class: "q-actions" });
      if (item.status === "error") {
        actions.append(el("button", {
          class: "btn btn-ghost btn-small", type: "button", text: "Retry",
          onclick: () => { item.status = "waiting"; item.message = ""; renderQueue(); processQueue(); },
        }));
      }
      if (item.status !== "reading") {
        actions.append(el("button", {
          class: "btn btn-link btn-small", type: "button", text: "Remove",
          "aria-label": `Remove ${item.file.name} from the queue`,
          onclick: () => { state.queue = state.queue.filter((q) => q.id !== item.id); renderQueue(); },
        }));
      }

      list.append(el("li", { class: "queue-item" },
        el("span", { class: `qi qi-${item.status}`, "aria-hidden": "true", text: STATUS_ICON[item.status] }),
        el("div", {},
          el("div", { class: "q-name", text: `${item.file.name} (${formatSize(item.file.size)})` }),
          el("div", {
            class: `q-status${item.status === "error" ? " is-error" : item.status === "done" ? " is-done" : ""}`,
            text: statusText(item),
          })),
        actions));
    });
  }

  async function processQueue() {
    if (state.processing) return;
    state.processing = true;
    $("resetBtn").disabled = true;

    try {
      let item;
      while ((item = state.queue.find((q) => q.status === "waiting"))) {
        item.status = "reading";
        item.elapsed = 0;
        renderQueue();

        const startedAt = Date.now();
        const timer = setInterval(() => {
          item.elapsed = Math.floor((Date.now() - startedAt) / 1000);
          renderQueue();
        }, 1000);

        try {
          const form = new FormData();
          form.append("file", item.file);
          const data = await api("/upload", { method: "POST", body: form });

          if (data.duplicate) {
            item.status = "duplicate";
            item.message = data.message;
            toast(data.message, "info");
          } else {
            const doc = data.document;
            item.status = "done";
            item.message = `${Object.keys(doc.facts || {}).length} facts, ${doc.chunk_count} chunks`;
            toast(`${item.file.name} added.`, "success");
          }
          await loadCase();
        } catch (err) {
          item.status = "error";
          item.message = err.message;
        } finally {
          clearInterval(timer);
          renderQueue();
        }
      }
    } finally {
      state.processing = false;
      $("resetBtn").disabled = false;
    }
  }

  // ---------- header actions ----------
  async function downloadJson() {
    try {
      const data = await api("/case?full=1");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = el("a", { href: url, download: `${data.case_id || "store"}.json` });
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast(`Download failed: ${err.message}`, "error");
    }
  }

  async function resetCase() {
    try {
      await api("/reset", { method: "POST" });
      state.queue = [];
      state.openDocs.clear();
      state.seenDocs.clear();
      renderQueue();
      await loadCase();
      toast("New case started. The old case was archived.", "success");
    } catch (err) {
      toast(`Could not reset: ${err.message}`, "error");
    }
  }

  // ---------- events ----------
  const dropzone = $("dropzone");
  const fileInput = $("fileInput");

  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      fileInput.click();
    }
  });
  ["dragenter", "dragover"].forEach((name) =>
    dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.add("is-drag"); }));
  ["dragleave", "drop"].forEach((name) =>
    dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.remove("is-drag"); }));
  dropzone.addEventListener("drop", (event) => addFiles(event.dataTransfer.files));

  // A file dropped outside the box should not make the browser open the PDF.
  ["dragover", "drop"].forEach((name) => window.addEventListener(name, (event) => event.preventDefault()));

  fileInput.addEventListener("change", () => {
    addFiles(fileInput.files);
    fileInput.value = "";
  });

  $("clearQueueBtn").addEventListener("click", () => {
    state.queue = state.queue.filter((q) => q.status === "reading" || q.status === "waiting");
    renderQueue();
  });

  $("search").addEventListener("input", (event) => {
    state.filter = event.target.value;
    renderDocs((state.store && state.store.documents) || []);
  });
  $("missingOnly").addEventListener("change", (event) => {
    state.missingOnly = event.target.checked;
    renderDocs((state.store && state.store.documents) || []);
  });

  $("downloadBtn").addEventListener("click", downloadJson);

  const resetDialog = $("resetDialog");
  $("resetBtn").addEventListener("click", () => {
    resetDialog.returnValue = "";
    resetDialog.showModal();
  });
  resetDialog.addEventListener("close", () => {
    if (resetDialog.returnValue === "confirm") resetCase();
  });

  $("drawerClose").addEventListener("click", closeDrawer);
  $("overlay").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && $("drawer").classList.contains("is-open") && !resetDialog.open) closeDrawer();
  });

  // ---------- start ----------
  loadCase();
})();