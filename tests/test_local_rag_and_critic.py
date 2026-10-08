"""Comprehensive Test Suite for Local Hybrid RAG & Agentic Critic.

Covers all 12 mandatory verification dimensions:
1. Correct retrieval
2. No-result query
3. Cross-case leakage (Case Isolation)
4. Unsupported claim detection
5. Citation correctness (Authentic metadata, zero hallucinated IDs)
6. Contradictory evidence detection
7. Missing information gate
8. BM25 keyword retrieval
9. Vector dense retrieval
10. Hybrid RAG fusion (RRF)
11. Critic rejection & fail-safe fallback
12. End-to-end RAG with Parquet streaming ingestion
"""
import os
import tempfile
from pathlib import Path
import pytest
import pyarrow as pa
import pyarrow.parquet as pq

from backend.critic import AgenticCritic, FALLBACK_MISSING_INFO
from backend.local_rag import LocalHybridRAG
from backend.local_pipeline import ingest_parquet, query_local_rag
from backend.models import MockLocalLLMProvider
from backend.parquet_loader import ParquetDatasetStreamer


@pytest.fixture
def rag_instance(tmp_path):
    """Provides a fresh isolated LocalHybridRAG instance."""
    return LocalHybridRAG(persist_dir=tmp_path / "chroma_test", collection_name="test_cases")


@pytest.fixture
def sample_chunks():
    """Sample legal evidentiary chunks spanning multiple cases."""
    return [
        {
            "chunk_id": "doc1-p1-para1",
            "case_id": "case_alpha",
            "doc_id": "doc1",
            "page": 1,
            "court": "High Court of Delhi",
            "date": "12-03-2025",
            "title": "State v. Ramesh Kumar",
            "source_url": "https://delhihighcourt.nic.in/cases/101",
            "text": "The petitioner Ramesh Kumar was arrested on 10th January 2025 under Section 420 IPC at Connaught Place.",
        },
        {
            "chunk_id": "doc1-p1-para2",
            "case_id": "case_alpha",
            "doc_id": "doc1",
            "page": 1,
            "court": "High Court of Delhi",
            "date": "12-03-2025",
            "title": "State v. Ramesh Kumar",
            "source_url": "https://delhihighcourt.nic.in/cases/101",
            "text": "The petitioner has no previous criminal antecedents and cooperated fully with the investigating officer.",
        },
        {
            "chunk_id": "doc2-p1-para1",
            "case_id": "case_beta",
            "doc_id": "doc2",
            "page": 1,
            "court": "High Court of Bombay",
            "date": "24-08-2024",
            "title": "Sunil Verma v. State of Maharashtra",
            "source_url": "https://bombayhighcourt.nic.in/cases/202",
            "text": "The applicant Sunil Verma was detained at Bandra Kurla Complex on 15th July 2024 concerning cheque dishonour.",
        },
    ]


# -----------------------------------------------------------------------------
# 1. Correct Retrieval Test
# -----------------------------------------------------------------------------
def test_correct_retrieval(rag_instance, sample_chunks):
    rag_instance.add_chunks(sample_chunks)
    results = rag_instance.retrieve_hybrid("Ramesh Kumar arrest Connaught Place Section 420", k=1)
    assert len(results) == 1
    assert results[0]["chunk_id"] == "doc1-p1-para1"
    assert "Ramesh Kumar" in results[0]["text"]


# -----------------------------------------------------------------------------
# 2. No-Result Query Test
# -----------------------------------------------------------------------------
def test_no_result_query(rag_instance, sample_chunks):
    rag_instance.add_chunks(sample_chunks)
    # Search for terms completely absent from corpus
    results = rag_instance.retrieve_bm25("xyzzy interstellar astrophysics spaceship", k=5)
    assert len(results) == 0


# -----------------------------------------------------------------------------
# 3. Cross-Case Leakage Test (Strict Case Isolation)
# -----------------------------------------------------------------------------
def test_cross_case_leakage(rag_instance, sample_chunks):
    rag_instance.add_chunks(sample_chunks)
    
    # Query for terms present in case_beta ("Bandra Kurla"), but restrict to case_alpha
    results = rag_instance.retrieve_hybrid("Bandra Kurla Sunil Verma", case_id="case_alpha", k=5)
    for r in results:
        assert r["case_id"] == "case_alpha", "Leakage detected: retrieved chunk belonging to another case!"
        assert r["chunk_id"] != "doc2-p1-para1"

    # Query for case_beta specifically
    results_beta = rag_instance.retrieve_hybrid("detained", case_id="case_beta", k=5)
    assert len(results_beta) == 1
    assert results_beta[0]["case_id"] == "case_beta"
    assert results_beta[0]["chunk_id"] == "doc2-p1-para1"


# -----------------------------------------------------------------------------
# 4. Unsupported Claim Detection Test
# -----------------------------------------------------------------------------
def test_unsupported_claim(sample_chunks):
    critic = AgenticCritic(min_confidence=0.7)
    retrieved = [sample_chunks[0]]  # Ramesh Kumar arrested under Section 420

    # Fabricated statement with unbacked entity and date
    proposed = "The petitioner Vikram Malhotra was convicted of murder on 25th December 2020."
    is_supported, chunk, reason = critic.evaluate_sentence(proposed, retrieved)
    
    assert not is_supported
    assert "Unsupported assertion" in reason


# -----------------------------------------------------------------------------
# 5. Citation Correctness Test (Authentic Metadata, Zero Fake IDs)
# -----------------------------------------------------------------------------
def test_citation_correctness(sample_chunks):
    critic = AgenticCritic(min_confidence=0.7)
    retrieved = [sample_chunks[0]]

    valid_claim = "Ramesh Kumar was arrested on 10th January 2025 under Section 420 IPC."
    audit = critic.audit_response(valid_claim, retrieved, case_id="case_alpha")

    assert audit["is_grounded"] is True
    assert len(audit["sources"]) == 1
    src = audit["sources"][0]
    assert src["case_id"] == "case_alpha"
    assert src["document"] == "doc1"
    assert src["source_id"] == "doc1-p1-para1"
    assert "Sources:" in audit["grounded_answer"]
    assert "[1] Case ID: case_alpha" in audit["grounded_answer"]
    assert "Source ID: doc1-p1-para1" in audit["grounded_answer"]


# -----------------------------------------------------------------------------
# 6. Contradictory Evidence Test
# -----------------------------------------------------------------------------
def test_contradictory_evidence(sample_chunks):
    critic = AgenticCritic(min_confidence=0.7)
    retrieved = [sample_chunks[1]]  # Source states petitioner has NO previous criminal antecedents

    contradictory_claim = "The petitioner Ramesh Kumar has 15 previous criminal antecedents and refused to cooperate."
    audit = critic.audit_response(contradictory_claim, retrieved, case_id="case_alpha")

    assert not audit["is_grounded"]
    assert audit["grounded_answer"] == FALLBACK_MISSING_INFO


# -----------------------------------------------------------------------------
# 7. Missing Information Gate Test
# -----------------------------------------------------------------------------
def test_missing_information():
    critic = AgenticCritic(min_confidence=0.7)
    # Evidence is empty or completely unrelated
    audit = critic.audit_response("The bail petition was filed yesterday.", [], case_id="case_alpha")

    assert not audit["is_grounded"]
    assert audit["grounded_answer"] == FALLBACK_MISSING_INFO
    assert audit["confidence"] == 0.0


# -----------------------------------------------------------------------------
# 8. BM25 Retrieval Test
# -----------------------------------------------------------------------------
def test_bm25_retrieval(rag_instance, sample_chunks):
    rag_instance.add_chunks(sample_chunks)
    res = rag_instance.retrieve_bm25("criminal antecedents officer", k=1)
    assert len(res) == 1
    assert res[0]["chunk_id"] == "doc1-p1-para2"
    assert res[0]["retrieval_type"] == "bm25"
    assert res[0]["score"] > 0


# -----------------------------------------------------------------------------
# 9. Vector Retrieval Test
# -----------------------------------------------------------------------------
def test_vector_retrieval(rag_instance, sample_chunks):
    rag_instance.add_chunks(sample_chunks)
    res = rag_instance.retrieve_vector("financial fraud cheque dishonour at Mumbai", k=1)
    assert len(res) == 1
    assert res[0]["chunk_id"] == "doc2-p1-para1"
    assert res[0]["retrieval_type"] == "vector"


# -----------------------------------------------------------------------------
# 10. Hybrid Retrieval Fusion Test (RRF)
# -----------------------------------------------------------------------------
def test_hybrid_retrieval(rag_instance, sample_chunks):
    rag_instance.add_chunks(sample_chunks)
    hybrid_res = rag_instance.retrieve_hybrid("Ramesh Kumar Section 420", k=2)
    assert len(hybrid_res) >= 1
    assert hybrid_res[0]["retrieval_type"] == "hybrid"
    assert "fused_score" in hybrid_res[0]
    assert hybrid_res[0]["chunk_id"] == "doc1-p1-para1"


# -----------------------------------------------------------------------------
# 11. Critic Rejection & Fail-Safe Fallback Test
# -----------------------------------------------------------------------------
def test_critic_rejection(sample_chunks):
    critic = AgenticCritic(min_confidence=0.7)
    # Propose 4 sentences where only 1 is supported (25% confidence < 70% threshold)
    proposed = (
        "Ramesh Kumar was arrested on 10th January 2025. "
        "He stole diamonds worth 500 million dollars from the central bank. "
        "The Supreme Court of Atlantis issued an extradition warrant. "
        "He escaped on a nuclear submarine."
    )
    audit = critic.audit_response(proposed, [sample_chunks[0]], case_id="case_alpha")

    assert not audit["is_grounded"]
    assert audit["confidence"] < 0.7
    assert audit["grounded_answer"] == FALLBACK_MISSING_INFO
    assert len(audit["rejected_assertions"]) >= 2


# -----------------------------------------------------------------------------
# 12. End-to-End RAG with Parquet Streaming Ingestion Test
# -----------------------------------------------------------------------------
def test_end_to_end_rag_with_parquet(tmp_path):
    parquet_path = tmp_path / "test_legal_dataset.parquet"
    
    # Generate authentic Parquet dataset with pyarrow
    table = pa.Table.from_pydict({
        "case_id": ["case_101", "case_102"],
        "doc_id": ["doc_101", "doc_102"],
        "text": [
            "The High Court granted anticipatory bail to applicant Priya Sharma on 05-02-2025 subject to 50000 bond.",
            "The commercial arbitral award between ABC Corp and XYZ Ltd was confirmed on 14-06-2024.",
        ],
        "court": ["High Court of Judicature", "Commercial Division"],
        "date": ["05-02-2025", "14-06-2024"],
        "title": ["Priya Sharma v. State", "ABC Corp v. XYZ Ltd"],
        "source_url": ["https://court.gov/101", "https://court.gov/102"],
    })
    pq.write_table(table, str(parquet_path))

    # Test Parquet Streamer
    streamer = ParquetDatasetStreamer(str(parquet_path))
    assert streamer.num_rows == 2
    chunks = list(streamer.stream_chunks(max_records=2))
    assert len(chunks) == 2
    assert chunks[0]["case_id"] == "case_101"

    # Index into RAG
    rag = LocalHybridRAG(persist_dir=tmp_path / "chroma_e2e")
    rag.add_chunks(chunks)
    assert rag.count() == 2

    # Query with Qwen/Gemma mock provider and Critic
    res = query_local_rag(
        question="What were the conditions of anticipatory bail for Priya Sharma?",
        case_id="case_101",
        k=2,
        min_confidence=0.7,
        provider_type="mock",
        rag_instance=rag,
    )

    assert res["retrieval_count"] == 1
    assert res["case_id"] == "case_101"
    assert "Priya Sharma" in res["retrieved_chunks"][0]["text"]
    assert res["is_grounded"] is True
    assert len(res["sources"]) == 1
    assert res["sources"][0]["case_id"] == "case_101"
    assert res["sources"][0]["document"] == "doc_101"
    assert "Answer:" in res["answer"]
    assert "Sources:" in res["answer"]


# -----------------------------------------------------------------------------
# 13. Trained Model Classification & Reranking Test
# -----------------------------------------------------------------------------
def test_trained_model_classification():
    from backend import trained_classifier

    # Test bail text
    bail_text = "The applicant prays for grant of pre-arrest anticipatory bail under Section 438 CrPC."
    res = trained_classifier.predict_category(bail_text)
    assert res["predicted_class"] == "bail_application"
    assert res["confidence"] > 0.5
    assert "probabilities" in res

    # Test legal notice text
    notice_text = "Statutory demand notice under Section 138 Negotiable Instruments Act for unpaid cheque."
    res_notice = trained_classifier.predict_category(notice_text)
    assert res_notice["predicted_class"] == "legal_notice"
    assert res_notice["confidence"] > 0.5

    # Test model metadata
    info = trained_classifier.get_model_info()
    assert info["status"] == "trained_and_operational"
    assert len(info["classes"]) == 5
    assert info["vocabulary_size"] > 0

    # Test RAG chunk reranking
    chunks = [
        {"chunk_id": "c1", "text": "Plaintiff filed civil suit for permanent injunction and partition.", "fused_score": 0.02},
        {"chunk_id": "c2", "text": "Petitioner arrested and seeks regular bail bond release.", "fused_score": 0.02},
    ]
    reranked = trained_classifier.score_and_rerank_chunks("bail surrender application", chunks)
    assert len(reranked) == 2
    assert reranked[0]["chunk_id"] == "c2"  # Bail chunk gets category match bonus!

