"""Feature 3: grounded drafting (bail application, legal notice, affidavit).

Pipeline: missing-info + contradiction report -> hybrid retrieval -> Gemini drafts JSON sentences
with chunk IDs and exact quotes -> Python validator (Feature 4) -> saved in store.json.
If Gemini is unavailable, a fact-only template draft is built from verified facts (backup mode),
and it goes through the same validator.
"""
import re
from datetime import datetime

from backend import analyzer, gemini_client, prompts, retrieval, storage, validator

MAX_PASSAGE_CHARS = 120_000

STRUCTURE = {
    "bail_application": {
        "title": "Bail Application",
        "sections": [("header", "Court and case details"), ("parties", "Parties"),
                     ("facts", "Facts of the case"), ("grounds", "Grounds for bail"),
                     ("prayer", "Prayer"), ("verification", "Verification")],
        "queries": ["grounds for bail", "reasons the accused will not abscond", "custody arrest surrender",
                    "age health occupation family of the accused", "allegations in the complaint"],
        "templates": {
            "prayer": ["It is therefore most respectfully prayed that the Ld. Court may be pleased to "
                       "grant bail to the accused person(s) on such terms and conditions as the Ld. Court "
                       "may deem fit and proper.",
                       "The accused person(s) undertake to abide by every condition that may be imposed "
                       "by the Ld. Court."],
            "verification": ["The contents of this application are true to the best of the knowledge "
                             "and belief of the applicant(s), and nothing material has been concealed."],
        },
    },
    "legal_notice": {
        "title": "Legal Notice",
        "sections": [("header", "Sender, recipient and date"), ("subject", "Subject"),
                     ("facts", "Facts"), ("demand", "Demand"),
                     ("consequence", "Consequence of non-compliance"), ("signature", "Signature")],
        "queries": ["sender and recipient of the notice", "amount due payment", "breach default",
                    "demand relief sought", "time limit to comply"],
        "templates": {
            "consequence": ["If the above demand is not complied with within the stipulated time, "
                            "appropriate legal proceedings may be initiated at your risk as to costs "
                            "and consequences."],
            "signature": ["Advocate: [information needed: name and enrolment number of the advocate]"],
        },
    },
    "affidavit": {
        "title": "Affidavit",
        "sections": [("header", "Court and case details"), ("deponent", "Deponent"),
                     ("statements", "Statements on oath"), ("verification", "Verification")],
        "queries": ["deponent name parentage age address", "statements of the deponent",
                    "petitioner applicant details"],
        "templates": {
            "verification": ["I, the deponent above named, do hereby verify that the contents of this "
                             "affidavit are true and correct to the best of my knowledge and belief, and "
                             "nothing material has been concealed therefrom.",
                             "Place and date of verification: [information needed: place and date]"],
        },
    },
}


# ---------- context building (shared with qa.py) ----------

def facts_block(documents, limit_chars=40_000):
    lines = []
    for d in documents:
        for key, f in d["facts"].items():
            lines.append(f"{d['doc_id']}.{key} = {f['value']} | {f['chunk_id']} | \"{f['quote']}\"")
    text = "\n".join(lines)
    return text[:limit_chars] or "(none)"


def passages_block(chunks, limit_chars=MAX_PASSAGE_CHARS):
    out, size = [], 0
    for c in chunks:
        line = f"[{c['chunk_id']}] {c['text']}"
        if size + len(line) > limit_chars:
            break
        out.append(line)
        size += len(line)
    return "\n".join(out) or "(none)"


def all_chunks(documents):
    return [c for d in documents for c in d["chunks"]]


def context_chunks(documents, queries, mode, use_retrieval, k_total=24):
    """Retrieved chunks (or all chunks for the no-retrieval ablation) + chunks behind every fact."""
    chunks = all_chunks(documents)
    by_id = {c["chunk_id"]: c for c in chunks}
    info = {"mode_used": "all chunks (no retrieval)", "notes": [], "chunk_ids": []}
    if use_retrieval:
        found = retrieval.retrieve_many([q for q in queries if q], k_each=4, mode=mode, k_total=k_total)
        info = {"mode_used": found["mode_used"], "notes": found["notes"],
                "chunk_ids": [r["chunk_id"] for r in found["results"]]}
        wanted = list(info["chunk_ids"])
        for d in documents:  # the chunks that verified facts came from are always included
            for f in d["facts"].values():
                if f["chunk_id"] not in wanted:
                    wanted.append(f["chunk_id"])
        selected = [by_id[i] for i in wanted if i in by_id]
    else:
        selected = chunks
        info["chunk_ids"] = [c["chunk_id"] for c in chunks]
    return selected, info


def _report_for(store, draft_type):
    """Uses the saved report if it still matches; otherwise builds it (Features 5 + 6)."""
    documents = store["documents"]
    doc_ids = [d["doc_id"] for d in documents]
    out = store.get("outputs") or {}
    contradictions = out.get("contradictions")
    if not contradictions or contradictions.get("doc_ids") != doc_ids:
        contradictions = analyzer.find_contradictions(documents)
        contradictions["doc_ids"] = doc_ids
        contradictions["analyzed_at"] = datetime.now().isoformat(timespec="seconds")
    missing = out.get("missing_info")
    if not missing or missing.get("doc_ids") != doc_ids or missing.get("draft_type") != draft_type:
        missing = analyzer.missing_info_report(documents, draft_type, contradictions)
        missing["doc_ids"] = doc_ids
        missing["analyzed_at"] = datetime.now().isoformat(timespec="seconds")
        storage.save_outputs(doc_ids, missing_info=missing, contradictions=contradictions)
    return missing, contradictions


# ---------- backup draft (no Gemini) ----------

_FALLBACK_SECTION = [
    (r"^(court|district|police_station|case|fir|crime|section|judge|order)", "header"),
    (r"^(complainant|informant|accused|other_accused|petitioner|applicant|deponent|sender|recipient|"
     r"addressee|noticee|client)", "parties"),
]


def _fallback_sections(documents, draft_type, missing):
    spec = STRUCTURE[draft_type]
    ids = [sid for sid, _ in spec["sections"]]
    sections = {sid: [] for sid in ids}

    def target(key):
        for pattern, sid in _FALLBACK_SECTION:
            if re.search(pattern, key):
                if sid in sections:
                    return sid
                return ids[1] if sid == "parties" else ids[0]
        return "facts" if "facts" in sections else ids[min(2, len(ids) - 1)]

    for d in documents:
        for key, f in d["facts"].items():
            # no digits in the label: the source may number people as (i), (ii) instead of 1, 2
            label = re.sub(r"\s+", " ", re.sub(r"[_\d]+", " ", key)).strip().lower()
            value = str(f["value"]).strip().rstrip(".")
            if validator.MISSING_TAG in value.lower():
                continue
            if value.upper() == "BLANK":
                text = f"As recorded, the {label} is left blank in the document."
            else:
                text = f"As recorded, {label}: {value}."
            sections[target(key)].append(
                {"text": text, "type": "fact", "citations": [{"chunk_id": f["chunk_id"], "quote": f["quote"]}]})

    gap_section = "facts" if "facts" in sections else ids[0]
    for field in missing["fields"]:
        if field["status"] != "found":
            sections[gap_section].append({"text": f"{field['label']}: [information needed: {field['label'].lower()}]",
                                          "type": "missing", "citations": []})
    for sid, lines in spec["templates"].items():
        sections[sid] += [{"text": t, "type": "template", "citations": []} for t in lines]
    return sections


# ---------- main ----------

def _normalise_sections(raw, draft_type):
    spec = STRUCTURE[draft_type]
    data = raw.get("sections", raw) if isinstance(raw, dict) else {}
    if isinstance(data, list):  # [{"id": ..., "sentences": [...]}]
        data = {str(s.get("id")): s.get("sentences", []) for s in data if isinstance(s, dict)}
    result = []
    for sid, heading in spec["sections"]:
        result.append({"id": sid, "heading": heading, "sentences": list(data.get(sid) or [])})
    for sid, sentences in data.items():  # keep any extra section Gemini added (it is validated too)
        if sid not in dict(spec["sections"]) and isinstance(sentences, list):
            result.append({"id": sid, "heading": sid.replace("_", " ").title(), "sentences": sentences})
    return result


def draft(draft_type, instructions="", retrieval_mode=retrieval.DEFAULT_MODE,
          use_retrieval=True, save=True, force_fallback=False):
    if draft_type not in STRUCTURE:
        raise ValueError(f"Unknown draft type: {draft_type}")
    store = storage.load_store()
    documents = store["documents"]
    if not documents:
        raise ValueError("Upload at least one document first.")
    doc_ids = [d["doc_id"] for d in documents]
    spec = STRUCTURE[draft_type]

    missing, contradictions = _report_for(store, draft_type)
    queries = [f["label"] for f in analyzer.DRAFT_TYPES[draft_type]["fields"]] + spec["queries"]
    if instructions.strip():
        queries.append(instructions.strip()[:300])
    notes = []
    try:
        selected, retrieval_info = context_chunks(documents, queries, retrieval_mode, use_retrieval)
    except Exception as e:  # retrieval problem: fall back to all chunks
        selected, retrieval_info = all_chunks(documents), {"mode_used": "all chunks", "notes": [str(e)[:200]], "chunk_ids": []}

    source = "gemini"
    raw_sections = None
    if not force_fallback:
        prompt = prompts.DRAFT_PROMPT.format(
            label=analyzer.DRAFT_TYPES[draft_type]["label"],
            sections="\n".join(f"- {sid}: {heading}" for sid, heading in spec["sections"]),
            missing="\n".join(f"- {f['label']} ({f['status']})" for f in missing["fields"]
                              if f["status"] != "found") or "(none)",
            contradictions="\n".join(
                f"- {c['topic']}: " + " vs ".join(f"{s['chunk_id']} \"{s['quote']}\"" for s in c["sides"])
                for c in contradictions["items"]) or "(none)",
            instructions=instructions.strip() or "(none)",
            facts=facts_block(documents),
            passages=passages_block(selected),
        )
        try:
            raw_sections = _normalise_sections(gemini_client.generate_json(prompt), draft_type)
            if not any(s["sentences"] for s in raw_sections):
                raise RuntimeError("Gemini returned an empty draft.")
        except Exception as e:
            notes.append(f"Gemini drafting failed, backup template draft used: {str(e)[:200]}")
            raw_sections = None
    if raw_sections is None:
        source = "backup_template"
        fb = _fallback_sections(documents, draft_type, missing)
        raw_sections = [{"id": sid, "heading": h, "sentences": fb[sid]} for sid, h in spec["sections"]]

    sections, removed, stats = validator.validate_draft(raw_sections, all_chunks(documents))
    result = {
        "draft_type": draft_type,
        "label": analyzer.DRAFT_TYPES[draft_type]["label"],
        "title": spec["title"],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "doc_ids": doc_ids,
        "source": source,
        "instructions": instructions,
        "retrieval": retrieval_info,
        "notes": notes + retrieval_info.get("notes", []),
        "readiness": missing["readiness"],
        "questions": missing["questions"],
        "contradiction_count": len(contradictions["items"]),
        "sections": sections,
        "removed": removed,
        "validation": stats,
    }
    if save:
        result["saved"] = storage.save_draft(doc_ids, draft_type, result)
    result["raw_sections"] = raw_sections  # for the ablation (not saved in store.json)
    return result


def revalidate(draft_type):
    """Runs the validator again on a saved draft (route /validate)."""
    store = storage.load_store()
    saved = (store.get("outputs") or {}).get("drafts", {}).get(draft_type)
    if not saved:
        raise ValueError("No saved draft of this type. Generate it first.")
    chunks = all_chunks(store["documents"])
    sections, removed, stats = validator.validate_draft(saved["sections"], chunks)
    return {"draft_type": draft_type, "validation": stats, "removed": removed,
            "problems": [p for s in sections for p in validator.audit(s["sentences"], chunks)]}


def as_text(result):
    """Plain-text version with [n] citation numbers and a source list (for download)."""
    lines, refs = [result["title"].upper(), ""], []
    for sec in result["sections"]:
        if not sec["sentences"]:
            continue
        lines.append(sec["heading"].upper())
        para = []
        for s in sec["sentences"]:
            marks = ""
            for c in s["citations"]:
                refs.append(c)
                marks += f"[{len(refs)}]"
            para.append(s["text"] + marks)
        lines += [" ".join(para), ""]
    lines.append("SOURCES")
    lines += [f"[{n}] {c['chunk_id']}: \"{c['quote']}\"" for n, c in enumerate(refs, start=1)]
    return "\n".join(lines)
