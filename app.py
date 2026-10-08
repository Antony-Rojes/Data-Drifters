from uuid import uuid4
import os
from flask import Flask, Response, jsonify, request, send_file, send_from_directory
from werkzeug.utils import secure_filename

from backend import analyzer, config, drafter, extractor, qa, retrieval, storage, validator
from backend import local_pipeline, local_rag, models

app = Flask(__name__, static_folder=str(config.FRONTEND_DIR), static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024


def _summary(doc):
    return {
        "doc_id": doc["doc_id"],
        "filename": doc["filename"],
        "page_count": doc["page_count"],
        "ocr_pages": doc["ocr_pages"],
        "document_type": doc["document_type"],
        "chunk_count": len(doc["chunks"]),
        "facts": doc["facts"],
        "unverified_facts": doc["unverified_facts"],
    }


def _run(fn, *args, **kwargs):
    """Common error handling: bad input -> 400, anything else -> 500 with a readable message."""
    try:
        return jsonify(fn(*args, **kwargs))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=f"{type(e).__name__}: {e}"), 500


# ---------- pages and documents ----------

@app.get("/")
def index():
    return send_from_directory(config.FRONTEND_DIR, "index.html")


@app.post("/upload")
def upload():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify(error="No file received."), 400
    if not file.filename.lower().endswith(".pdf"):
        return jsonify(error="Only PDF files are supported."), 400

    filename = secure_filename(file.filename) or "document.pdf"
    tmp_path = config.UPLOAD_DIR / f"_tmp_{uuid4().hex}.pdf"
    final_path = None
    file.save(tmp_path)

    try:
        sha = extractor.file_hash(tmp_path)
        existing = storage.find_by_hash(sha)
        if existing:
            tmp_path.unlink(missing_ok=True)
            return jsonify(duplicate=True, doc_id=existing["doc_id"],
                           message=f"{filename} was already uploaded as {existing['doc_id']}.")

        doc_id = storage.reserve_doc_id()
        final_path = config.UPLOAD_DIR / f"{doc_id}_{filename}"
        tmp_path.replace(final_path)

        doc = extractor.process_pdf(final_path, doc_id, filename, sha)
        storage.add_document(doc)

        # Sync document chunks into local ChromaDB + BM25
        try:
            local_pipeline.sync_store_to_local_rag()
        except Exception:
            pass

        return jsonify(duplicate=False, document=_summary(doc))
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        if final_path:
            final_path.unlink(missing_ok=True)
        return jsonify(error=str(e)), 500


@app.get("/case")
def get_case():
    store = storage.load_store()
    if request.args.get("full") == "1":
        store.pop("embeddings", None)  # vectors are internal; keep the response small
        return jsonify(store)
    return jsonify(case_id=store["case_id"],
                   documents=[_summary(d) for d in store["documents"]])


@app.get("/chunk/<chunk_id>")
def get_chunk(chunk_id):
    """Source viewer: the chunk plus its neighbours, so a citation can be checked in context."""
    store = storage.load_store()
    for doc in store["documents"]:
        for i, chunk in enumerate(doc["chunks"]):
            if chunk["chunk_id"] == chunk_id:
                return jsonify(doc_id=doc["doc_id"], filename=doc["filename"], chunk=chunk,
                               before=doc["chunks"][i - 1] if i > 0 else None,
                               after=doc["chunks"][i + 1] if i + 1 < len(doc["chunks"]) else None)
    return jsonify(error=f"Chunk {chunk_id} is not in this case."), 404


@app.get("/pdf/<doc_id>")
def get_pdf(doc_id):
    store = storage.load_store()
    doc = next((d for d in store["documents"] if d["doc_id"] == doc_id), None)
    if not doc:
        return jsonify(error="Unknown document."), 404
    path = config.UPLOAD_DIR / f"{doc_id}_{secure_filename(doc['filename']) or 'document.pdf'}"
    if not path.exists():
        return jsonify(error="The PDF file is no longer on disk."), 404
    return send_file(path, mimetype="application/pdf")


@app.post("/reset")
def reset():
    store = storage.reset_store()
    return jsonify(ok=True, case_id=store["case_id"])


# ---------- features 5 + 6: report before drafting ----------

@app.get("/draft-types")
def draft_types():
    return jsonify(analyzer.draft_type_list())


@app.post("/analyze")
def analyze():
    body = request.get_json(silent=True) or {}
    return _run(analyzer.analyze_case, body.get("draft_type", analyzer.DEFAULT_DRAFT_TYPE))


# ---------- feature 2: retrieval ----------

@app.post("/retrieve")
def retrieve():
    body = request.get_json(silent=True) or {}
    return _run(retrieval.retrieve, body.get("query", ""), k=int(body.get("k", 8)),
                mode=body.get("mode", retrieval.DEFAULT_MODE), doc_ids=body.get("doc_ids"))


# ---------- features 3 + 4: drafting and validation ----------

def _draft(body):
    result = drafter.draft(body.get("draft_type", analyzer.DEFAULT_DRAFT_TYPE),
                           instructions=str(body.get("instructions", ""))[:2000],
                           retrieval_mode=body.get("mode", retrieval.DEFAULT_MODE))
    result.pop("raw_sections", None)
    return result


@app.post("/draft")
def draft():
    return _run(_draft, request.get_json(silent=True) or {})


@app.get("/draft/<draft_type>.txt")
def draft_text(draft_type):
    store = storage.load_store()
    saved = (store.get("outputs") or {}).get("drafts", {}).get(draft_type)
    if not saved:
        return jsonify(error="No saved draft of this type."), 404
    return Response(drafter.as_text(saved), mimetype="text/plain",
                    headers={"Content-Disposition": f"attachment; filename={draft_type}.txt"})


def _validate(body):
    if body.get("sentences") is not None:
        chunks = drafter.all_chunks(storage.load_store()["documents"])
        sentences, removed, stats = validator.validate_sentences(body["sentences"], chunks)
        return {"sentences": sentences, "removed": removed, "validation": stats}
    return drafter.revalidate(body.get("draft_type", analyzer.DEFAULT_DRAFT_TYPE))


@app.post("/validate")
def validate():
    return _run(_validate, request.get_json(silent=True) or {})


# ---------- workflow 4: grounded Q&A with Agentic Critic ----------

def _ask(body):
    history = body.get("history") if isinstance(body.get("history"), list) else []
    result = qa.answer(str(body.get("question", ""))[:1000], history=history,
                       mode=body.get("mode", retrieval.DEFAULT_MODE))
    result.pop("raw_sentences", None)
    return result


@app.post("/ask")
def ask():
    return _run(_ask, request.get_json(silent=True) or {})


# ---------- Local Hybrid RAG, Parquet Ingestion & Critic APIs ----------

@app.post("/rag/ask")
def rag_ask():
    """Direct query to the Local Hybrid RAG + Agentic Critic pipeline."""
    body = request.get_json(silent=True) or {}
    question = str(body.get("question", "")).strip()
    if not question:
        return jsonify(error="Question is required."), 400

    store = storage.load_store()
    local_pipeline.sync_store_to_local_rag(case_id=store.get("case_id"))
    case_id = body.get("case_id") or store.get("case_id")
    k = int(body.get("k", 5))
    min_confidence = float(body.get("min_confidence", 0.7))
    provider = body.get("provider")

    return _run(
        local_pipeline.query_local_rag,
        question=question,
        case_id=case_id,
        k=k,
        min_confidence=min_confidence,
        provider_type=provider,
    )


@app.post("/parquet/ingest")
def parquet_ingest():
    """Stream and ingest a Parquet dataset into ChromaDB and BM25 index."""
    body = request.get_json(silent=True) or {}
    file_path = body.get("file_path")
    if not file_path:
        return jsonify(error="file_path is required."), 400
    max_records = int(body.get("max_records", 5000))
    chunk_size = int(body.get("chunk_size_chars", 1000))

    return _run(
        local_pipeline.ingest_parquet,
        file_path=file_path,
        max_records=max_records,
        chunk_size_chars=chunk_size,
    )


@app.get("/rag/stats")
def rag_stats():
    """Inspect local ChromaDB collection, active cases, and model config."""
    rag = local_rag.get_local_rag()
    store = storage.load_store()
    llm = models.get_llm_provider()
    return jsonify({
        "status": "operational",
        "chroma_total_chunks": rag.count(),
        "active_case_id": store.get("case_id"),
        "active_case_chunks": rag.count(case_id=store.get("case_id")),
        "model_provider": type(llm).__name__,
        "model_name": getattr(llm, "model_name", "unknown"),
        "critic_threshold": 0.7,
    })


# ---------- Trained Machine Learning Model APIs ----------

@app.post("/model/predict")
def model_predict():
    """Classify legal text into document categories using trained scikit-learn model."""
    from backend import trained_classifier
    body = request.get_json(silent=True) or {}
    text = body.get("text", "")
    return jsonify(trained_classifier.predict_category(text))


@app.get("/model/info")
def model_info():
    """Inspect parameters and classes of the locally trained legal classifier."""
    from backend import trained_classifier
    return jsonify(trained_classifier.get_model_info())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"Starting Legal Assistant at http://127.0.0.1:{port}")
    app.run(debug=True, port=port, host="127.0.0.1")
