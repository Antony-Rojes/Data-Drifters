import json
import os
import tempfile
import threading
from datetime import datetime

from backend import config

_lock = threading.Lock()


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _empty_store():
    return {
        "case_id": datetime.now().strftime("case_%Y%m%d_%H%M%S"),
        "updated_at": _now(),
        "doc_counter": 0,
        "documents": [],
        "outputs": {"missing_info": None, "contradictions": None, "drafts": {}},
    }


def _write(store):
    """Write to a temp file, then replace. A crash can't corrupt store.json."""
    store["updated_at"] = _now()
    fd, tmp_path = tempfile.mkstemp(dir=config.CACHE_DIR, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, config.STORE_PATH)


def _read():
    if not config.STORE_PATH.exists():
        store = _empty_store()
        _write(store)
        return store
    with open(config.STORE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_store():
    with _lock:
        return _read()


def reserve_doc_id():
    """Hands out doc1, doc2, ... and never reuses an ID."""
    with _lock:
        store = _read()
        store["doc_counter"] = store.get("doc_counter", 0) + 1
        _write(store)
        return f"doc{store['doc_counter']}"


def find_by_hash(file_hash):
    store = load_store()
    for doc in store["documents"]:
        if doc.get("file_hash") == file_hash:
            return doc
    return None


def add_document(doc):
    """Appends to the single store.json. Old reports and drafts become outdated, so they are cleared."""
    with _lock:
        store = _read()
        store["documents"].append(doc)
        store["outputs"] = {"missing_info": None, "contradictions": None, "drafts": {}}
        _write(store)
        return store


def reset_store():
    """New Case: archive the current store, then start a fresh one."""
    with _lock:
        if config.STORE_PATH.exists():
            old = _read()
            if old["documents"]:
                archive_path = config.ARCHIVE_DIR / f"{old['case_id']}.json"
                with open(archive_path, "w", encoding="utf-8") as f:
                    json.dump(old, f, ensure_ascii=False, indent=2)
        store = _empty_store()
        _write(store)
        return store

def save_outputs(expected_doc_ids, **outputs):
    """Saves reports into store["outputs"], but only if the documents did not change meanwhile."""
    with _lock:
        store = _read()
        if [d["doc_id"] for d in store["documents"]] != list(expected_doc_ids):
            return False  # a new upload happened during analysis; this report is outdated
        store["outputs"].update(outputs)
        _write(store)
        return True


def save_embeddings(model, dims, new_vectors):
    """Caches chunk meaning-vectors inside store.json so each chunk is embedded only once."""
    with _lock:
        store = _read()
        live = {c["chunk_id"] for d in store["documents"] for c in d["chunks"]}
        cache = store.get("embeddings") or {}
        if cache.get("model") != model or cache.get("dims") != dims:
            cache = {"model": model, "dims": dims, "vectors": {}}
        for chunk_id, vector in new_vectors.items():
            if chunk_id in live:  # ignore chunks removed by New Case meanwhile
                cache["vectors"][chunk_id] = [round(float(x), 5) for x in vector]
        store["embeddings"] = cache
        _write(store)


def save_draft(expected_doc_ids, draft_type, draft):
    """Saves a validated draft into store["outputs"]["drafts"] if the documents did not change."""
    with _lock:
        store = _read()
        if [d["doc_id"] for d in store["documents"]] != list(expected_doc_ids):
            return False
        store["outputs"].setdefault("drafts", {})[draft_type] = draft
        _write(store)
        return True
