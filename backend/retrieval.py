"""Feature 2: hybrid retrieval = BM25 keywords + Gemini embeddings (meaning) + Gemini reranker.

Modes (also used for the ablation in eval):
  "bm25"          keywords only (baseline)
  "dense"         meaning only
  "hybrid"        BM25 + meaning, merged with Reciprocal Rank Fusion
  "hybrid_rerank" hybrid, then Gemini re-scores the top passages (default)

Retrieval only RANKS real chunks from store.json. It never writes text, so it cannot add a
fabricated fact. If Gemini is down, it falls back to BM25 and says so in "notes".
"""
import math
import re
import sys

import numpy as np
from rank_bm25 import BM25Okapi

from backend import config, gemini_client, prompts, storage

MODES = ("bm25", "dense", "hybrid", "hybrid_rerank")
DEFAULT_MODE = "hybrid_rerank"
RRF_K = 60            # standard constant for Reciprocal Rank Fusion
RERANK_POOL = 20      # how many fused results the reranker looks at
MIN_CHUNK_CHARS = 12  # skip noise like "Contd.....2"

_STOP = {
    "a", "an", "the", "of", "to", "in", "on", "at", "by", "for", "and", "or", "is", "are", "was",
    "were", "be", "been", "has", "have", "had", "that", "this", "with", "as", "it", "its", "from",
    "what", "which", "who", "whom", "when", "where", "how", "does", "did", "do", "any", "there",
}


def _stem(word):
    for suffix in ("ing", "ed", "es", "ly", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokenize(text):
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _STOP]


# ---------- the three signals ----------

def _bm25_ranking(chunks, query):
    q = tokenize(query)
    if not q:
        return []
    corpus = [tokenize(c["text"]) or ["_empty_"] for c in chunks]
    bm25 = BM25Okapi(corpus)
    # Lucene-style IDF: always positive, so common words like "bail" still count in small cases.
    n_docs = len(corpus)
    doc_freq = {}
    for doc in corpus:
        for word in set(doc):
            doc_freq[word] = doc_freq.get(word, 0) + 1
    bm25.idf = {w: math.log(1 + (n_docs - n + 0.5) / (n + 0.5)) for w, n in doc_freq.items()}
    scores = bm25.get_scores(q)
    ranked = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    return [(i, float(scores[i])) for i in ranked if scores[i] > 0]


def _chunk_vectors(chunks):
    """Embeds chunks once and caches the vectors in store.json."""
    cache = storage.load_store().get("embeddings") or {}
    same_model = cache.get("model") == config.GEMINI_EMBED_MODEL and cache.get("dims") == config.EMBED_DIMS
    vectors = dict(cache.get("vectors", {})) if same_model else {}

    todo = [c for c in chunks if c["chunk_id"] not in vectors]
    if todo:
        new = gemini_client.embed_texts([c["text"][:8000] for c in todo], "RETRIEVAL_DOCUMENT")
        new = {c["chunk_id"]: v for c, v in zip(todo, new)}
        storage.save_embeddings(config.GEMINI_EMBED_MODEL, config.EMBED_DIMS, new)
        vectors.update(new)
    return vectors


def _dense_ranking(chunks, query):
    vectors = _chunk_vectors(chunks)
    matrix = np.array([vectors[c["chunk_id"]] for c in chunks], dtype=float)
    q = np.array(gemini_client.embed_texts([query], "RETRIEVAL_QUERY")[0], dtype=float)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
    q /= np.linalg.norm(q) + 1e-9
    sims = matrix @ q
    ranked = np.argsort(-sims)
    return [(int(i), float(sims[i])) for i in ranked]


def _rerank(chunks, pool, query):
    """Gemini scores the pool 0-10. Unknown chunk IDs are ignored."""
    passages = "\n".join(f"[{chunks[i]['chunk_id']}] {chunks[i]['text'][:1500]}" for i in pool)
    raw = gemini_client.generate_json(
        prompts.RERANK_PROMPT + f"QUERY: {query}\n\nPASSAGES:\n{passages}")
    allowed = {chunks[i]["chunk_id"]: i for i in pool}
    scores = {}
    for item in (raw.get("scores") or []) if isinstance(raw, dict) else []:
        cid = item.get("chunk_id")
        try:
            score = max(0.0, min(10.0, float(item.get("score"))))
        except (TypeError, ValueError):
            continue
        if cid in allowed:
            scores[allowed[cid]] = score
    if not scores:
        raise RuntimeError("Reranker returned no usable scores.")
    return scores


# ---------- main entry ----------

def _case_chunks(doc_ids=None):
    store = storage.load_store()
    return [c for d in store["documents"] if not doc_ids or d["doc_id"] in doc_ids
            for c in d["chunks"] if len(c["text"].strip()) >= MIN_CHUNK_CHARS]


def retrieve(query, k=8, mode=DEFAULT_MODE, doc_ids=None):
    query = (query or "").strip()
    if not query:
        raise ValueError("Query is empty.")
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode}. Use one of {MODES}.")
    chunks = _case_chunks(doc_ids)
    if not chunks:
        raise ValueError("No documents to search. Upload documents first.")

    notes, used = [], []
    bm25, dense = [], []

    if mode != "dense":
        bm25 = _bm25_ranking(chunks, query)
        used.append("bm25")
    if mode != "bm25":
        try:
            dense = _dense_ranking(chunks, query)
            used.append("dense")
        except Exception as e:
            notes.append(f"Meaning search skipped: {str(e)[:200]}")
            if mode == "dense":  # dense was the only signal: fall back to keywords
                bm25 = _bm25_ranking(chunks, query)
                used.append("bm25 (fallback)")

    # Reciprocal Rank Fusion: a chunk ranked high by either method rises to the top.
    fused = {}
    for ranking in (bm25, dense):
        for rank, (i, _) in enumerate(ranking, start=1):
            fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank)
    order = sorted(fused, key=lambda i: fused[i], reverse=True)

    rerank_scores = {}
    if mode == "hybrid_rerank" and order:
        pool = order[:RERANK_POOL]
        try:
            rerank_scores = _rerank(chunks, pool, query)
            used.append("rerank")
            pool.sort(key=lambda i: (rerank_scores.get(i, -1), fused[i]), reverse=True)
            order = pool + order[RERANK_POOL:]
        except Exception as e:
            notes.append(f"Reranker skipped: {str(e)[:200]}")

    bm25_rank = {i: r for r, (i, _) in enumerate(bm25, start=1)}
    dense_rank = {i: r for r, (i, _) in enumerate(dense, start=1)}
    results = []
    for i in order[:k]:
        c = chunks[i]
        results.append({
            "chunk_id": c["chunk_id"],
            "doc_id": c["chunk_id"].split("-")[0],
            "page": c["page"],
            "text": c["text"],
            "fused_score": round(fused[i], 5),
            "bm25_rank": bm25_rank.get(i),
            "dense_rank": dense_rank.get(i),
            "rerank_score": rerank_scores.get(i),
        })
    return {"query": query, "mode_requested": mode, "mode_used": "+".join(used),
            "notes": notes, "results": results}


def retrieve_many(queries, k_each=5, mode=DEFAULT_MODE, doc_ids=None, k_total=20):
    """Several queries at once (used by drafting). Keeps each chunk once, at its best position."""
    best, notes, modes = {}, [], set()
    for q in queries:
        out = retrieve(q, k=k_each, mode=mode, doc_ids=doc_ids)
        notes += out["notes"]
        modes.add(out["mode_used"])
        for pos, r in enumerate(out["results"]):
            if r["chunk_id"] not in best or pos < best[r["chunk_id"]][0]:
                best[r["chunk_id"]] = (pos, r, q)
    merged = sorted(best.values(), key=lambda t: (t[0], -t[1]["fused_score"]))
    results = [dict(r, matched_query=q) for _, r, q in merged[:k_total]]
    return {"queries": queries, "mode_used": ", ".join(sorted(modes)),
            "notes": sorted(set(notes)), "results": results}


if __name__ == "__main__":
    # Quick test: python -m backend.retrieval "is the accused surrendering" hybrid_rerank
    text = sys.argv[1] if len(sys.argv) > 1 else "accused surrender bail"
    run_mode = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MODE
    output = retrieve(text, k=5, mode=run_mode)
    print(f"Mode used: {output['mode_used']}")
    for note in output["notes"]:
        print("Note:", note)
    for n, r in enumerate(output["results"], start=1):
        print(f"{n}. [{r['chunk_id']}] bm25#{r['bm25_rank']} dense#{r['dense_rank']} "
              f"rerank={r['rerank_score']} | {r['text'][:110]}")
