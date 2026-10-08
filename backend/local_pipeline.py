"""End-to-End Local Hybrid RAG + Agentic Critic Pipeline.

Orchestrates:
Parquet → document loader → chunking → embeddings → ChromaDB
                                  +
                              BM25 index
                                  ↓
                         Hybrid retrieval
                                  ↓
                           Qwen/Gemma
                                  ↓
                         Agentic Critic
                                  ↓
                      Grounded final answer
"""
from typing import Any, Dict, List, Optional

from backend import storage
from backend.critic import AgenticCritic, DEFAULT_MIN_CONFIDENCE
from backend.local_rag import get_local_rag
from backend.models import get_llm_provider
from backend.parquet_loader import ParquetDatasetStreamer


def ingest_parquet(
    file_path: str,
    max_records: Optional[int] = 5000,
    chunk_size_chars: int = 1000,
    rag_instance: Optional[Any] = None,
) -> Dict[str, Any]:
    """Streams a Parquet dataset from disk and indexes it into local ChromaDB + BM25."""
    streamer = ParquetDatasetStreamer(file_path)
    rag = rag_instance or get_local_rag()

    chunks_batch: List[Dict[str, Any]] = []
    total_chunks = 0
    total_records = 0
    seen_cases = set()

    for chunk in streamer.stream_chunks(chunk_size_chars=chunk_size_chars, max_records=max_records):
        chunks_batch.append(chunk)
        seen_cases.add(chunk.get("case_id"))
        total_chunks += 1

        if len(chunks_batch) >= 500:
            rag.add_chunks(chunks_batch)
            chunks_batch = []

    if chunks_batch:
        rag.add_chunks(chunks_batch)

    return {
        "status": "success",
        "file_path": file_path,
        "indexed_chunks": total_chunks,
        "cases_indexed": len(seen_cases),
        "total_collection_size": rag.count(),
    }


def sync_store_to_local_rag(case_id: Optional[str] = None, rag_instance: Optional[Any] = None) -> int:
    """Syncs existing uploaded matter documents from storage (store.json) into the local RAG."""
    store = storage.load_store()
    c_id = case_id or store.get("case_id", "default_case")
    documents = store.get("documents") or []
    rag = rag_instance or get_local_rag()

    chunks_to_add: List[Dict[str, Any]] = []
    for doc in documents:
        doc_id = doc.get("doc_id", "doc1")
        for c in doc.get("chunks", []):
            chunks_to_add.append({
                "chunk_id": c["chunk_id"],
                "case_id": c_id,
                "doc_id": doc_id,
                "page": c.get("page", 1),
                "court": doc.get("court", ""),
                "date": doc.get("date", ""),
                "title": doc.get("filename", ""),
                "source_url": f"/chunk/{c['chunk_id']}",
                "text": c.get("text", ""),
            })

    if chunks_to_add:
        rag.add_chunks(chunks_to_add)
    return len(chunks_to_add)


def query_local_rag(
    question: str,
    case_id: Optional[str] = None,
    k: int = 5,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    provider_type: Optional[str] = None,
    rag_instance: Optional[Any] = None,
) -> Dict[str, Any]:
    """Executes the full local hybrid RAG + Agentic Critic pipeline:
    1. Hybrid retrieval (ChromaDB vector + BM25) with Case Isolation
    2. Local Open-Weight LLM generation (Qwen / Gemma)
    3. Agentic Critic pre-audit interceptor & groundedness gate
    """
    rag = rag_instance or get_local_rag()

    # Step 1: Hybrid Retrieval with Case Isolation
    retrieved_chunks = rag.retrieve_hybrid(query=question, case_id=case_id, k=k)

    # Step 2: Handle empty retrieval boundary
    if not retrieved_chunks:
        critic = AgenticCritic(min_confidence=min_confidence)
        audit_res = critic.audit_response(
            proposed_answer="",
            retrieved_chunks=[],
            case_id=case_id,
        )
        return {
            "question": question,
            "case_id": case_id,
            "answer": audit_res["grounded_answer"],
            "confidence": 0.0,
            "is_grounded": False,
            "retrieval_count": 0,
            "retrieved_chunks": [],
            "sources": [],
            "audit_log": audit_res["audit_log"],
        }

    # Step 3: Local Model Reasoning (Qwen / Gemma / Local Provider - NO Gemini)
    passages_text = "\n\n".join(
        f"[{c['chunk_id']}] (Doc: {c.get('doc_id')}, Page: {c.get('page')})\n{c['text']}"
        for c in retrieved_chunks
    )

    prompt = (
        f"QUESTION: {question}\n\n"
        f"VERIFIED EVIDENCE PASSAGES:\n{passages_text}\n\n"
        "INSTRUCTIONS:\n"
        "State only factual claims that are directly substantiated by the evidence above. "
        "Do not invent facts, dates, names, or citations. Keep the response precise and legally grounded."
    )
    system_prompt = (
        "You are a rigorous legal reasoning engine operating under a strict zero-fabrication protocol. "
        "Every claim must be strictly anchored in the provided evidence passages."
    )

    llm = get_llm_provider(provider_type)
    try:
        raw_answer = llm.generate(prompt=prompt, system_prompt=system_prompt, temperature=0.1)
    except Exception as e:
        # Extractive fallback directly from top verified passages
        top_text = retrieved_chunks[0]["text"][:250].strip()
        raw_answer = f"The verified case filings record that {top_text}."

    # Step 4: Agentic Critic Pre-Audit Interceptor
    critic = AgenticCritic(min_confidence=min_confidence)
    audit = critic.audit_response(
        proposed_answer=raw_answer,
        retrieved_chunks=retrieved_chunks,
        case_id=case_id,
    )

    return {
        "question": question,
        "case_id": case_id,
        "answer": audit["grounded_answer"],
        "answer_body": audit.get("answer_body", ""),
        "confidence": audit["confidence"],
        "is_grounded": audit["is_grounded"],
        "retrieval_count": len(retrieved_chunks),
        "retrieved_chunks": retrieved_chunks,
        "sources": audit["sources"],
        "audit_log": audit["audit_log"],
        "raw_answer": raw_answer,
    }
