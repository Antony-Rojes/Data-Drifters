import hashlib
import re
from datetime import datetime

import fitz  # PyMuPDF

from backend import config, gemini_client, prompts


def file_hash(path):
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def _norm(text):
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _text_paragraphs(page):
    paragraphs = []
    for block in page.get_text("blocks", sort=True):
        if block[6] != 0:  # skip image blocks
            continue
        text = re.sub(r"\s*\n\s*", " ", block[4]).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def _ocr_paragraphs(page):
    png = page.get_pixmap(dpi=200).tobytes("png")
    text = gemini_client.ocr_page(png)
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def parse_pdf(path, doc_id):
    """PDF -> list of chunks with stable IDs like doc1-p3-para2."""
    chunks, ocr_pages = [], []
    with fitz.open(path) as pdf:
        page_count = len(pdf)
        for page_no, page in enumerate(pdf, start=1):
            paragraphs = _text_paragraphs(page)
            source = "text_layer"
            if sum(len(p) for p in paragraphs) < config.OCR_MIN_CHARS:
                paragraphs = _ocr_paragraphs(page)
                source = "ocr"
                ocr_pages.append(page_no)
            for n, text in enumerate(paragraphs, start=1):
                chunks.append({
                    "chunk_id": f"{doc_id}-p{page_no}-para{n}",
                    "page": page_no,
                    "paragraph": n,
                    "text": text,
                    "source": source,
                })
    if not chunks:
        raise ValueError("No readable text was found in this PDF.")
    return chunks, page_count, ocr_pages


def extract_facts(chunks):
    """Gemini proposes facts. Code keeps only those whose quote really exists in the source."""
    document = "\n".join(f"[{c['chunk_id']}] {c['text']}" for c in chunks)
    raw = gemini_client.generate_json(prompts.FACTS_PROMPT + document)

    by_id = {c["chunk_id"]: c for c in chunks}
    facts, dropped = {}, []

    for item in raw.get("facts", []):
        key = re.sub(r"\W+", "_", str(item.get("key", "")).strip().lower()).strip("_")
        value = item.get("value")
        quote = str(item.get("quote") or "")
        claimed_id = item.get("chunk_id")
        if not key or value in (None, "") or len(quote) < 3:
            continue

        verified_id = None
        if claimed_id in by_id and _norm(quote) in _norm(by_id[claimed_id]["text"]):
            verified_id = claimed_id
        else:  # Gemini gave the wrong chunk ID; look for the quote anywhere
            for c in chunks:
                if _norm(quote) in _norm(c["text"]):
                    verified_id = c["chunk_id"]
                    break

        if not verified_id:
            dropped.append(key)
            continue

        final_key, i = key, 2
        while final_key in facts:
            final_key = f"{key}_{i}"
            i += 1
        facts[final_key] = {"value": str(value), "chunk_id": verified_id, "quote": quote}

    return raw.get("document_type", "other"), facts, dropped


def process_pdf(path, doc_id, filename, sha):
    chunks, page_count, ocr_pages = parse_pdf(path, doc_id)
    document_type, facts, dropped = extract_facts(chunks)
    return {
        "doc_id": doc_id,
        "filename": filename,
        "file_hash": sha,
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "page_count": page_count,
        "ocr_pages": ocr_pages,
        "document_type": document_type,
        "chunks": chunks,
        "facts": facts,
        "unverified_facts": dropped,
    }