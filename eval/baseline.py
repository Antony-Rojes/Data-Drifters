"""Baseline = plain Gemini on the same document text.
No chunk IDs, no retrieval, no structured citations, no validator. Same model as our system.
It is told to use only the documents, so it is a fair (not a straw-man) baseline."""
from backend import gemini_client

QA_PROMPT = """You are a legal assistant. Answer the question about this Indian legal case.
Use only the case documents below.

CASE DOCUMENTS:
{docs}

QUESTION: {question}

ANSWER:"""

DRAFT_PROMPT = """You are an Indian legal drafting assistant. Draft a complete {label} for this case.
Use only the case documents below.

CASE DOCUMENTS:
{docs}

DRAFT:"""


def documents_text(documents):
    parts = []
    for d in documents:
        parts.append(f"--- {d['filename']} ---")
        parts.append("\n".join(c["text"] for c in d["chunks"]))
    return "\n\n".join(parts)


def answer(question, documents):
    return gemini_client.generate_text(QA_PROMPT.format(docs=documents_text(documents), question=question))


def draft(label, documents):
    return gemini_client.generate_text(DRAFT_PROMPT.format(docs=documents_text(documents), label=label))
