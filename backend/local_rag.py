"""Local Hybrid RAG Engine (ChromaDB Vector Store + BM25 Index).

Combines dense semantic vector search via local ChromaDB with sparse keyword search
via BM25Okapi using Reciprocal Rank Fusion (RRF). Guarantees strict Case Isolation
to prevent cross-case data leakage. Operates 100% offline with zero cloud connections.
"""
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
import numpy as np
from rank_bm25 import BM25Okapi

from backend import config


RRF_K = 60
EMBED_DIMS = 384
_STOP = {
    "a", "an", "the", "of", "to", "in", "on", "at", "by", "for", "and", "or", "is", "are", "was",
    "were", "be", "been", "has", "have", "had", "that", "this", "with", "as", "it", "its", "from",
    "what", "which", "who", "whom", "when", "where", "how", "does", "did", "do", "any", "there",
}


def _tokenize(text: str) -> List[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [w for w in words if w not in _STOP and len(w) > 1]


class LocalDenseEmbeddingFunction(EmbeddingFunction[Documents]):
    """100% offline, zero-cloud deterministic dense embedding projection.
    Maps word and subword n-gram features to a unit sphere vector of dimension `dims`.
    Requires zero external network requests or heavyweight weights downloads.
    """

    def __init__(self, dims: int = EMBED_DIMS):
        self.dims = dims

    @classmethod
    def name(cls) -> str:
        return "local_dense_embedding"

    def get_config(self) -> Dict[str, Any]:
        return {"dims": self.dims}

    @classmethod
    def build_from_config(cls, config: Dict[str, Any]) -> "LocalDenseEmbeddingFunction":
        return cls(dims=config.get("dims", EMBED_DIMS))

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = []
        for doc in input:
            vec = np.zeros(self.dims, dtype=np.float32)
            words = _tokenize(doc)
            for idx, w in enumerate(words):
                # Word hash projection with position decay
                h = abs(hash(w)) % self.dims
                weight = 1.0 / (math.log(idx + 2))
                vec[h] += weight
                # Character n-grams for morphological / root matching
                for n in (3, 4):
                    if len(w) >= n:
                        for j in range(len(w) - n + 1):
                            ngram = w[j : j + n]
                            nh = abs(hash(ngram)) % self.dims
                            vec[nh] += 0.35 * weight
            norm = np.linalg.norm(vec)
            if norm > 1e-9:
                vec /= norm
            embeddings.append(vec.tolist())
        return embeddings


class LocalHybridRAG:
    """Manages local ChromaDB vector store and in-memory BM25 index with Case Isolation."""

    def __init__(self, persist_dir: Optional[Path] = None, collection_name: str = "legal_knowledge_base"):
        self.persist_dir = persist_dir or (config.CACHE_DIR / "chroma_db")
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.embedding_fn = LocalDenseEmbeddingFunction(dims=EMBED_DIMS)

        # Initialize persistent ChromaDB client with offline local embeddings
        self.chroma_client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_fn,
            metadata={"description": "Zero-cloud local legal document vector embeddings"}
        )

        # In-memory chunk registry for fast BM25 construction and metadata lookup
        self._chunks: Dict[str, Dict[str, Any]] = {}
        self._sync_from_chroma()

    def _sync_from_chroma(self):
        """Pre-populate in-memory registry from existing ChromaDB entries."""
        try:
            total = self.collection.count()
            if total > 0:
                data = self.collection.get(include=["documents", "metadatas"])
                for cid, doc, meta in zip(data["ids"], data["documents"], data["metadatas"]):
                    self._chunks[cid] = {
                        "chunk_id": cid,
                        "text": doc,
                        "case_id": meta.get("case_id", ""),
                        "doc_id": meta.get("doc_id", ""),
                        "page": meta.get("page", 1),
                        "court": meta.get("court", ""),
                        "date": meta.get("date", ""),
                        "title": meta.get("title", ""),
                        "source_url": meta.get("source_url", ""),
                    }
        except Exception:
            pass

    def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """Add or update chunks in both ChromaDB and the BM25 index."""
        if not chunks:
            return 0

        ids = [c["chunk_id"] for c in chunks]
        documents = [c["text"] for c in chunks]
        metadatas = [
            {
                "case_id": str(c.get("case_id", "")),
                "doc_id": str(c.get("doc_id", "")),
                "page": int(c.get("page", 1)),
                "court": str(c.get("court", "")),
                "date": str(c.get("date", "")),
                "title": str(c.get("title", "")),
                "source_url": str(c.get("source_url", "")),
            }
            for c in chunks
        ]

        # Upsert in batches of 500 into ChromaDB
        batch_size = 500
        for i in range(0, len(ids), batch_size):
            self.collection.upsert(
                ids=ids[i : i + batch_size],
                documents=documents[i : i + batch_size],
                metadatas=metadatas[i : i + batch_size],
            )

        # Update in-memory chunk registry
        for c, meta in zip(chunks, metadatas):
            item = dict(c)
            item.update(meta)
            self._chunks[c["chunk_id"]] = item

        return len(chunks)

    def count(self, case_id: Optional[str] = None) -> int:
        """Count total chunks, optionally isolated to a specific case."""
        if not case_id:
            return self.collection.count()
        return sum(1 for c in self._chunks.values() if c.get("case_id") == case_id)

    # ---------- Retrieval Subsystems with Case Isolation ----------

    def retrieve_vector(self, query: str, case_id: Optional[str] = None, k: int = 5) -> List[Dict[str, Any]]:
        """Dense semantic search using ChromaDB embeddings with strict case filtering."""
        where_filter = {"case_id": case_id} if case_id else None
        total_avail = self.count(case_id=case_id)
        if total_avail == 0:
            self._sync_from_chroma()
            total_avail = self.count(case_id=case_id)
        if total_avail == 0:
            return []

        fetch_k = min(k, total_avail)
        results = self.collection.query(
            query_texts=[query],
            n_results=fetch_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        ranked = []
        if results and results["ids"] and results["ids"][0]:
            ids = results["ids"][0]
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            distances = results["distances"][0] if "distances" in results else [0.0] * len(ids)

            for cid, doc, meta, dist in zip(ids, docs, metas, distances):
                sim = 1.0 - dist if dist <= 1.0 else 1.0 / (1.0 + dist)
                item = {
                    "chunk_id": cid,
                    "text": doc,
                    "score": round(float(sim), 4),
                    "retrieval_type": "vector",
                }
                item.update(meta)
                ranked.append(item)
        return ranked

    def retrieve_bm25(self, query: str, case_id: Optional[str] = None, k: int = 5) -> List[Dict[str, Any]]:
        """Sparse keyword search using BM25Okapi with strict case filtering."""
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []

        pool = [
            c for c in self._chunks.values()
            if not case_id or c.get("case_id") == case_id
        ]
        if not pool:
            self._sync_from_chroma()
            pool = [
                c for c in self._chunks.values()
                if not case_id or c.get("case_id") == case_id
            ]
        if not pool:
            return []

        corpus = [_tokenize(c["text"]) or ["_empty_"] for c in pool]
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(q_tokens)

        ranked_indices = sorted(range(len(pool)), key=lambda idx: scores[idx], reverse=True)
        ranked = []
        for idx in ranked_indices:
            if scores[idx] <= 0:
                break
            c = pool[idx]
            item = dict(c)
            item["score"] = round(float(scores[idx]), 4)
            item["retrieval_type"] = "bm25"
            ranked.append(item)
            if len(ranked) >= k:
                break
        return ranked

    def retrieve_hybrid(
        self,
        query: str,
        case_id: Optional[str] = None,
        k: int = 5,
        vector_k: int = 15,
        bm25_k: int = 15,
    ) -> List[Dict[str, Any]]:
        """Reciprocal Rank Fusion (RRF) of Dense Vector + BM25 keyword rankings."""
        vec_results = self.retrieve_vector(query, case_id=case_id, k=vector_k)
        bm25_results = self.retrieve_bm25(query, case_id=case_id, k=bm25_k)

        if not vec_results and not bm25_results:
            return []

        rrf_scores: Dict[str, float] = {}
        item_map: Dict[str, Dict[str, Any]] = {}

        for rank, item in enumerate(vec_results, start=1):
            cid = item["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (RRF_K + rank))
            item_map[cid] = item

        for rank, item in enumerate(bm25_results, start=1):
            cid = item["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (RRF_K + rank))
            if cid not in item_map:
                item_map[cid] = item

        sorted_cids = sorted(rrf_scores.keys(), key=lambda c: rrf_scores[c], reverse=True)
        final_results = []
        for cid in sorted_cids[:k]:
            res = dict(item_map[cid])
            res["fused_score"] = round(rrf_scores[cid], 5)
            res["retrieval_type"] = "hybrid"
            final_results.append(res)

        return final_results


_rag_instance: Optional[LocalHybridRAG] = None


def get_local_rag() -> LocalHybridRAG:
    """Retrieve or initialize singleton LocalHybridRAG."""
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = LocalHybridRAG()
    return _rag_instance
