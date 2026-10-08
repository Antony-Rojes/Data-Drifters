// ============================================================================
// AGENTIC LEGAL ASSISTANT — GROUNDED AI ASSISTANT & CITATION WORKSPACE
// Multi-turn legal reasoning grounded strictly in evidence records
// ============================================================================

const chatLog = document.getElementById("chatLog");
const askInput = document.getElementById("askInput");
const askBtn = document.getElementById("askBtn");
const clearChatBtn = document.getElementById("clearChatBtn");
const askStatus = document.getElementById("askStatus");
const chatSourcesPane = document.getElementById("chatSourcesPane");

let chatHistory = [];
let chatCaseId = null;

function clearChat() {
  chatHistory = [];
  if (chatLog) {
    chatLog.replaceChildren();
    const welcome = el("div", undefined, "chat-welcome-card");
    welcome.append(
      icon("bot", "welcome-bot-icon"),
      el("h4", "Grounded AI Legal Assistant"),
      el("p", "Every response is synthesized strictly from your case filings and audited for hallucinations before delivery.", "text-muted"),
      el("div", "Select a suggested inquiry below or ask a custom legal question:", "welcome-hint")
    );
    chatLog.append(welcome);
  }
  if (chatSourcesPane) {
    chatSourcesPane.replaceChildren(
      el("div", "Evidence passages cited by the assistant will appear here in real time.", "empty-sources-note")
    );
  }
}

function updateAssistantSourcesPane(citations) {
  if (!chatSourcesPane) return;
  chatSourcesPane.replaceChildren();

  if (!citations || !citations.length) {
    chatSourcesPane.append(
      el("div", "No documentary citations required for this response.", "empty-sources-note")
    );
    return;
  }

  const head = el("div", undefined, "sources-pane-head");
  head.append(
    el("strong", `Cited Documentary Evidence (${citations.length})`),
    el("span", "Click chunk to view full context", "text-xs text-muted")
  );
  chatSourcesPane.append(head);

  citations.forEach((c, idx) => {
    const card = el("div", undefined, "evidence-passage-card");
    const top = el("div", undefined, "evidence-card-top");
    top.append(el("span", `[${idx + 1}]`, "citation-index-badge"), cidButton(c.chunk_id, c.quote));
    card.append(top);

    if (c.quote) {
      card.append(el("p", `"${c.quote}"`, "evidence-passage-quote"));
    }
    chatSourcesPane.append(card);
  });
}

function addAnswer(data) {
  const box = el("div", undefined, "chat-bubble bubble-assistant");

  const assistantHeader = el("div", undefined, "bubble-header");
  assistantHeader.append(
    icon("bot", "bubble-header-icon"),
    el("strong", "Counsel Assistant"),
    el("span", "Grounded Analysis", "badge-pill badge-primary")
  );
  box.append(assistantHeader);

  const refs = [];
  const contentBody = el("div", undefined, "bubble-content");
  contentBody.append(sentencesParagraph(data.sentences, refs));
  box.append(contentBody);

  const v = data.validation;
  const auditBadge = el("div", undefined, "bubble-audit-badge");
  let note = `${v.verified + v.repaired} assertion(s) verified in evidence`;
  if (v.replaced + v.removed) {
    note += `, ${v.replaced + v.removed} unbacked statement(s) pruned`;
  }
  if (data.source === "extractive_backup") {
    note += ". Extractive mode: quoted directly from source records";
  }

  auditBadge.append(icon("shieldCheck", "icon-verified"), el("span", `${note}.`));
  box.append(auditBadge);

  chatLog.append(box);
  chatLog.scrollTop = chatLog.scrollHeight;

  // Update live right-hand sources pane
  updateAssistantSourcesPane(refs);

  return data.sentences.map((s) => s.text).join(" ");
}

async function ask(customQuestion) {
  const question = (customQuestion || askInput.value || "").trim();
  if (!question) return;

  // Remove welcome card if this is the first question
  if (!chatHistory.length) {
    const welcome = chatLog.querySelector(".chat-welcome-card");
    if (welcome) welcome.remove();
  }

  // User bubble
  const userBox = el("div", undefined, "chat-bubble bubble-user");
  const userHeader = el("div", undefined, "bubble-header");
  userHeader.append(icon("user", "bubble-header-icon"), el("strong", "Counsel Inquiry"));
  userBox.append(userHeader, el("p", question, "bubble-content"));
  chatLog.append(userBox);
  chatLog.scrollTop = chatLog.scrollHeight;

  askInput.value = "";
  askBtn.disabled = true;
  if (askStatus) askStatus.textContent = "Retrieving relevant passages and synthesizing verified response...";

  // Loading indicator bubble
  const loadingBubble = el("div", undefined, "chat-bubble bubble-assistant bubble-loading");
  loadingBubble.append(
    icon("refresh", "icon-spin"),
    el("span", "Searching case filings and checking citations...")
  );
  chatLog.append(loadingBubble);
  chatLog.scrollTop = chatLog.scrollHeight;

  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history: chatHistory }),
    });
    const data = await res.json();
    loadingBubble.remove();

    if (!res.ok) {
      const errBox = el("div", undefined, "chat-bubble bubble-assistant bubble-error");
      errBox.append(icon("alertTriangle", "icon-warn"), el("p", data.error || "Failed to generate answer."));
      chatLog.append(errBox);
    } else {
      const answerText = addAnswer(data);
      chatHistory.push({ question, answer: answerText });
      if (typeof logActivity === "function") {
        logActivity("Assistant Queried", `Inquiry: "${question.slice(0, 45)}..."`, "info");
      }
    }
    if (askStatus) askStatus.textContent = "";
  } catch (err) {
    loadingBubble.remove();
    if (askStatus) askStatus.textContent = err.message;
    toast(`Inquiry error: ${err.message}`, "error");
  } finally {
    askBtn.disabled = false;
    askInput.focus();
  }
}

// Setup suggested questions
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".suggested-q-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const q = btn.dataset.query || btn.textContent.trim();
      ask(q);
    });
  });
});

askBtn.addEventListener("click", () => ask());
askInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    ask();
  }
});
clearChatBtn.addEventListener("click", clearChat);

document.addEventListener("case-changed", (e) => {
  const id = e.detail && e.detail.caseId;
  if (id !== chatCaseId) {
    chatCaseId = id;
    clearChat();
  }
});

clearChat();
