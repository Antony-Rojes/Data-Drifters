"""Workflow 4 (RAG chat): grounded multi-turn Q&A over the case documents.

Uses the local open-weight model integration (Qwen / Gemma) and passes every proposed
answer through the Agentic Critic pre-audit interceptor before return.
Guarantees zero-fabrication and strict source metadata adherence.
"""
from typing import Any, Dict, List, Optional

from backend import drafter, prompts, retrieval, storage, validator
from backend.critic import AgenticCritic, FALLBACK_MISSING_INFO
from backend.local_pipeline import sync_store_to_local_rag
from backend.models import get_llm_provider


def _history_text(history: Optional[List[Dict[str, str]]]) -> str:
    lines = []
    for turn in (history or [])[-4:]:
        lines.append(f"Q: {str(turn.get('question', ''))[:300]}")
        lines.append(f"A: {str(turn.get('answer', ''))[:600]}")
    return "\n".join(lines) or "(none)"


def _extractive_sentences(question: str, selected: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sentences = [
        {
            "text": "[information needed: local model offline, displaying verified passages]",
            "type": "missing",
            "citations": [],
        }
    ]
    for c in selected[:2]:
        quote = c["text"][:200]
        sentences.append({
            "text": f"The documents state: \"{quote}\"",
            "type": "fact",
            "citations": [{"chunk_id": c["chunk_id"], "quote": quote}],
        })
    return sentences


def answer(
    question: str,
    history: Optional[List[Dict[str, str]]] = None,
    mode: str = retrieval.DEFAULT_MODE,
    use_retrieval: bool = True,
    k: int = 8,
    min_confidence: float = 0.7,
) -> Dict[str, Any]:
    question = (question or "").strip()
    if not question:
        raise ValueError("Question is empty.")
    store = storage.load_store()
    documents = store.get("documents") or []
    if not documents:
        raise ValueError("Upload at least one document first.")
    chunks = drafter.all_chunks(documents)
    case_id = store.get("case_id", "default_case")

    # Sync documents into ChromaDB vector store
    try:
        sync_store_to_local_rag(case_id=case_id)
    except Exception:
        pass

    queries = [question]
    if history:
        queries.append(f"{history[-1].get('question', '')} {question}")
    notes = []

    if use_retrieval:
        found = retrieval.retrieve_many(queries, k_each=k, mode=mode, k_total=k)
        by_id = {c["chunk_id"]: c for c in chunks}
        selected = [by_id[r["chunk_id"]] for r in found["results"] if r["chunk_id"] in by_id]
        info = {"mode_used": found["mode_used"], "chunk_ids": [c["chunk_id"] for c in selected]}
        notes += found["notes"]
    else:
        selected = chunks
        info = {"mode_used": "all chunks (no retrieval)", "chunk_ids": [c["chunk_id"] for c in chunks]}

    # Local Model Generation (Qwen / Gemma / Local OpenAI Provider - NO Gemini)
    llm = get_llm_provider()
    source = getattr(llm, "model_name", "local_model")
    raw_sentences = []

    prompt = (
        f"QUESTION: {question}\n\n"
        f"VERIFIED EVIDENCE PASSAGES:\n{drafter.passages_block(selected)}\n\n"
        f"KNOWN FACTS:\n{drafter.facts_block(documents, 10_000)}\n\n"
        "INSTRUCTIONS:\n"
        "Generate a structured legal response. Answer in JSON with key 'sentences': [{\"text\": \"...\", \"citations\": [{\"chunk_id\": \"...\", \"quote\": \"...\"}]}]"
    )
    system_prompt = (
        "You are an expert legal assistant. Every factual statement must cite exact chunk IDs "
        "and verbatim quotes from the verified passages."
    )

    try:
        raw = llm.generate_json(prompt=prompt, system_prompt=system_prompt)
        raw_sentences = raw.get("sentences") if isinstance(raw, dict) else None
        if not raw_sentences:
            raise RuntimeError("Local model returned empty sentences structure.")
    except Exception as e:
        notes.append(f"Local model generation fallback: {str(e)[:160]}")
        source = "extractive_backup"
        raw_sentences = _extractive_sentences(question, selected)

    # Deterministic Sentence Validator
    sentences, removed, stats = validator.validate_sentences(raw_sentences, chunks)

    # Agentic Critic Pre-Audit Interceptor
    proposed_text = " ".join(s["text"] for s in sentences if s.get("text"))
    critic = AgenticCritic(min_confidence=min_confidence)
    critic_audit = critic.audit_response(
        proposed_answer=proposed_text,
        retrieved_chunks=selected,
        case_id=case_id,
    )

    # Enforce Hard Fail-Safe: If Critic halts or confidence < min_confidence
    if not critic_audit["is_grounded"] or not sentences:
        sentences = [{
            "text": FALLBACK_MISSING_INFO,
            "type": "missing",
            "citations": [],
            "status": "missing",
            "issues": ["critic_unresolved_boundary"],
        }]
        stats["critic_status"] = "REJECTED"
        stats["critic_confidence"] = critic_audit["confidence"]
    else:
        stats["critic_status"] = "VERIFIED"
        stats["critic_confidence"] = critic_audit["confidence"]

    return {
        "question": question,
        "sentences": sentences,
        "removed": removed,
        "validation": stats,
        "retrieval": info,
        "source": source,
        "notes": notes,
        "raw_sentences": raw_sentences,
        "critic_audit": critic_audit,
    }
