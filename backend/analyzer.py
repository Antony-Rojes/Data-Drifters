"""Features 5 + 6: missing-info / confidence report and contradiction detection.

Everything this module shows the user is either
  - a fact already stored in store.json (its quote was verified at upload), or
  - a quote that Python has found inside a stored chunk.
Gemini only SUGGESTS contradictions. Code checks every quote before keeping it.
"""
import re
from datetime import datetime
from itertools import combinations

from backend import gemini_client, prompts, storage

MAX_PROMPT_CHARS = 400_000
DEFAULT_DRAFT_TYPE = "bail_application"


def _f(field_id, label, pattern, importance, hints):
    return {"id": field_id, "label": label, "pattern": pattern,
            "importance": importance, "hints": hints}


# What each draft type needs. "pattern" is matched against fact keys in store.json.
DRAFT_TYPES = {
    "bail_application": {
        "label": "Bail application",
        "fields": [
            _f("court", "Court", r"^court", "required", ["court", "magistrate", "judge"]),
            _f("district", "District", r"^district", "recommended", ["district"]),
            _f("police_station", "Police station", r"police_station", "required", ["p.s.", "police station"]),
            _f("case_number", "Case / FIR number", r"^(case|fir|crime)_?(no|num)", "required", ["case no", "fir no", "f.i.r"]),
            _f("sections_of_law", "Sections of law", r"section", "required", ["u/s", "section", "sections"]),
            _f("complainant", "Complainant", r"complainant|informant", "required", ["complainant", "informant", "de facto"]),
            _f("accused_names", "Accused name(s)", r"^accused(_\d+)?_name$", "required", ["accused"]),
            _f("accused_addresses", "Accused address(es)", r"^accused(_\d+)?_address", "recommended", ["resident", "residing", "address"]),
            _f("custody_status", "Arrest / custody / surrender status", r"arrest|custody|surrender", "required", ["arrest", "arrested", "custody", "surrender", "surrendering"]),
            _f("date_of_incident", "Date of incident", r"(incident|occurrence|offence)_date|date_of_(incident|occurrence|offence)", "recommended", ["incident", "occurrence"]),
            _f("date_of_fir", "Date of FIR", r"fir_date|date_of_fir", "recommended", ["lodged", "registered"]),
            _f("previous_bail", "Previous bail applications / orders", r"(previous|prior|earlier)_bail|bail_order", "recommended", ["previous", "earlier", "rejected"]),
            _f("advocate", "Advocate for the accused", r"advocate|counsel", "recommended", ["advocate", "counsel"]),
        ],
    },
    "legal_notice": {
        "label": "Legal notice",
        "fields": [
            _f("sender", "Sender (on whose behalf)", r"^(sender|client|issuer)", "required", ["on behalf of", "my client"]),
            _f("recipient", "Recipient name", r"^(recipient|addressee|noticee)(_name)?$", "required", ["addressee", "noticee"]),
            _f("recipient_address", "Recipient address", r"^(recipient|addressee|noticee)_address", "required", ["address", "resident"]),
            _f("subject", "Subject / matter", r"subject|matter", "required", ["subject", "re:"]),
            _f("demand", "Demand / relief sought", r"demand|relief|claim", "required", ["demand", "call upon", "relief"]),
            _f("amount", "Amount involved", r"amount", "recommended", ["rs", "rupees", "₹"]),
            _f("deadline", "Time given to comply", r"deadline|time_limit|days", "recommended", ["within", "days"]),
            _f("advocate", "Advocate issuing the notice", r"advocate|counsel", "recommended", ["advocate", "counsel"]),
        ],
    },
    "affidavit": {
        "label": "Affidavit",
        "fields": [
            _f("deponent", "Deponent name", r"^(deponent|petitioner|applicant)(_\d+)?(_name)?$", "required", ["deponent", "petitioner"]),
            _f("deponent_relation", "Deponent's father / husband", r"^(deponent|petitioner|applicant)(_\d+)?_(father|husband|relation|parent)", "required", ["s/o", "d/o", "w/o", "son of", "wife of", "daughter of"]),
            _f("deponent_age", "Deponent's age", r"^(deponent|petitioner|applicant)(_\d+)?_age", "required", ["aged", "years"]),
            _f("deponent_address", "Deponent's address", r"^(deponent|petitioner|applicant)(_\d+)?_address", "required", ["resident", "residing"]),
            _f("deponent_occupation", "Deponent's occupation", r"^(deponent|petitioner|applicant)(_\d+)?_occupation", "recommended", ["occupation", "by profession"]),
            _f("court", "Court", r"^court", "recommended", ["court", "magistrate"]),
            _f("case_number", "Case number", r"^(case|fir|crime)_?(no|num)", "recommended", ["case no"]),
            _f("place", "Place of signing", r"^place|place_of", "recommended", ["place"]),
        ],
    },
}

# Keys that should have ONE value per case. Different values across documents = contradiction.
SINGLE_VALUED = {
    "court", "district", "police_station", "case_number", "case_no", "fir_number", "fir_no",
    "sections_of_law", "complainant_name", "date_of_incident", "date_of_fir", "date_of_arrest",
    "judge_name", "order_date",
}

_STOPWORDS = {
    "the", "of", "at", "in", "and", "ld", "learned", "hon", "ble", "honble", "smt", "sri", "shri",
    "mr", "mrs", "ms", "dr", "u", "s", "us", "ps", "p", "police", "station", "i", "c", "ipc",
    "no", "section", "sections", "sec", "court",
}
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


# ---------- small helpers ----------

def _canon(text):
    """Lower-case, same quotes/dashes, single spaces. Used for quote matching."""
    text = (text or "").replace("\u00a0", " ")
    text = re.sub(r"[\u2018\u2019\u201b`]", "'", text)
    text = re.sub(r"[\u201c\u201d\u201f]", '"', text)
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _is_blank(value):
    return str(value or "").strip().upper() in ("", "BLANK")


def _all_chunks(documents):
    return [c for d in documents for c in d["chunks"]]


def _doc_of(chunk_id):
    return chunk_id.split("-")[0]


def _value_signature(key, value):
    """Turns a value into something comparable: a date tuple for date keys, else a set of words."""
    text = str(value).lower()
    if "date" in key:
        m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", text)
        if m:
            d, mo, y = (int(x) for x in m.groups())
            return ("date", (y + 2000 if y < 100 else y, mo, d))
        m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3})[a-z]*,?\s+(\d{4})", text)
        if m and m.group(2) in _MONTHS:
            return ("date", (int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1))))
    words = set(re.findall(r"[a-z0-9]+", text)) - _STOPWORDS
    return ("words", frozenset(words))


def _overlap(a, b):
    """True if one quote contains the other (after normalising)."""
    a, b = _canon(a), _canon(b)
    return bool(a and b) and (a in b or b in a)


def _same_conflict(x, y):
    """Two contradiction items describe the same conflict if every side of x matches a side of y."""
    return all(any(sx["chunk_id"] == sy["chunk_id"] and _overlap(sx["quote"], sy["quote"])
                   for sy in y["sides"]) for sx in x["sides"])


def _locate_quote(quote, chunk_id, by_id, chunks):
    """Returns the chunk that really contains the quote, or None. Pure Python, no Gemini."""
    q = _canon(quote)
    if len(q.replace(" ", "")) < 5 or len(q) > 400:
        return None
    if chunk_id in by_id and q in _canon(by_id[chunk_id]["text"]):
        return by_id[chunk_id]
    for c in chunks:  # Gemini gave the wrong chunk ID; look for the quote anywhere
        if q in _canon(c["text"]):
            return c
    return None


# ---------- Feature 6: contradictions ----------

def _rule_contradictions(documents):
    """Same single-valued key, different values, in different documents."""
    groups = {}
    for d in documents:
        for key, fact in d["facts"].items():
            base = re.sub(r"_\d+$", "", key)
            if base in SINGLE_VALUED and not _is_blank(fact["value"]):
                groups.setdefault(base, []).append((d["doc_id"], key, fact))

    found = []
    for base, items in groups.items():
        for (doc_a, _, a), (doc_b, _, b) in combinations(items, 2):
            if doc_a == doc_b:
                continue
            sig_a, sig_b = _value_signature(base, a["value"]), _value_signature(base, b["value"])
            if sig_a == sig_b:
                continue
            partial = sig_a[0] == sig_b[0] == "words" and (sig_a[1] <= sig_b[1] or sig_b[1] <= sig_a[1])
            if partial and base != "sections_of_law":
                continue  # one is just a shorter form of the other ("Barasat" vs "ACJM at Barasat")
            found.append({
                "topic": base.replace("_", " "),
                "explanation": ("One document lists fewer items than the other."
                                if partial else "The documents state different values for this fact."),
                "severity": "low" if partial else "high",
                "detected_by": "rule",
                "sides": [
                    {"doc_id": doc_a, "chunk_id": a["chunk_id"], "quote": a["quote"], "value": a["value"]},
                    {"doc_id": doc_b, "chunk_id": b["chunk_id"], "quote": b["quote"], "value": b["value"]},
                ],
            })
    return found


def _gemini_text(documents):
    parts = []
    for d in documents:
        parts.append(f"=== {d['doc_id']} ({d['document_type']}, {d['filename']}) ===")
        parts.extend(f"[{c['chunk_id']}] {c['text']}" for c in d["chunks"])
    text = "\n".join(parts)
    if len(text) <= MAX_PROMPT_CHARS:
        return text
    # Too long: send only the verified facts (their quotes are still real chunk text).
    parts = []
    for d in documents:
        parts.append(f"=== {d['doc_id']} ({d['document_type']}) ===")
        parts.extend(f"[{f['chunk_id']}] {k}: {f['quote']}" for k, f in d["facts"].items())
    return "\n".join(parts)[:MAX_PROMPT_CHARS]


def _gemini_contradictions(documents):
    chunks = _all_chunks(documents)
    by_id = {c["chunk_id"]: c for c in chunks}
    raw = gemini_client.generate_json(prompts.CONTRADICTION_PROMPT + _gemini_text(documents))
    proposed = (raw.get("contradictions") or []) if isinstance(raw, dict) else []

    kept, dropped = [], 0
    for item in proposed:
        sides, seen = [], set()
        for side in item.get("sides") or []:
            quote = str(side.get("quote") or "").strip()
            chunk = _locate_quote(quote, side.get("chunk_id"), by_id, chunks)
            if chunk and (chunk["chunk_id"], _canon(quote)) not in seen:
                seen.add((chunk["chunk_id"], _canon(quote)))
                sides.append({"doc_id": _doc_of(chunk["chunk_id"]),
                              "chunk_id": chunk["chunk_id"], "quote": quote})
        # Keep it only if two verified sides exist and they are not the very same text.
        if len(sides) < 2 or len({_canon(s["quote"]) for s in sides}) < 2:
            dropped += 1
            continue
        severity = str(item.get("severity", "medium")).lower()
        kept.append({
            "topic": str(item.get("topic") or "conflict")[:80],
            "explanation": str(item.get("explanation") or "")[:300],
            "severity": severity if severity in ("high", "medium", "low") else "medium",
            "detected_by": "gemini",
            "sides": sides,
        })
    return kept, dropped


def find_contradictions(documents):
    items = _rule_contradictions(documents)
    report = {"checked_by": ["rule"], "gemini_error": None, "dropped_unverified": 0}

    try:
        gemini_items, report["dropped_unverified"] = _gemini_contradictions(documents)
        report["checked_by"].append("gemini")
        rule_items = list(items)
        for it in gemini_items:
            match = next((r for r in rule_items if _same_conflict(it, r) or _same_conflict(r, it)), None)
            if match:
                match["detected_by"] = "rule+gemini"
            else:
                items.append(it)
    except Exception as e:  # Gemini down (503 etc.): rule-based results still work
        report["gemini_error"] = str(e)[:300]

    order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda it: order[it["severity"]])
    for n, it in enumerate(items, start=1):
        it["id"] = f"c{n}"
        it["scope"] = ("cross-document" if len({s["doc_id"] for s in it["sides"]}) > 1
                       else "within-document")
    report["items"] = items
    return report


# ---------- Feature 5: missing info + confidence ----------

def _possible_mentions(documents, hints, limit=3):
    """For a missing field: real passages containing a hint word, so a human can check them."""
    out = []
    for c in _all_chunks(documents):
        text = c["text"].lower()
        if any(re.search(r"(?<!\w)" + re.escape(h) + r"(?!\w)", text) for h in hints):
            out.append({"chunk_id": c["chunk_id"], "text": c["text"][:200]})
            if len(out) >= limit:
                break
    return out


def missing_info_report(documents, draft_type, contradictions):
    spec = DRAFT_TYPES[draft_type]
    conflict_sides = [(s, it["severity"]) for it in contradictions["items"] for s in it["sides"]]

    fields, questions = [], []
    for field in spec["fields"]:
        sources = [
            {"doc_id": d["doc_id"], "key": key, "value": f["value"],
             "chunk_id": f["chunk_id"], "quote": f["quote"]}
            for d in documents for key, f in d["facts"].items()
            if re.search(field["pattern"], key)
        ]
        filled = [s for s in sources if not _is_blank(s["value"])]

        if filled:
            status = "found"
            docs = {s["doc_id"] for s in filled}
            hit = {sev for src in filled for side, sev in conflict_sides
                   if src["chunk_id"] == side["chunk_id"] and _overlap(src["quote"], side["quote"])}
            if hit - {"low"}:
                confidence, reason = "low", "conflicting values in the sources"
            elif hit:
                confidence, reason = "medium", "sources partly differ"
            elif len(docs) > 1:
                confidence, reason = "high", f"confirmed by {len(docs)} documents"
            else:
                confidence, reason = "medium", "stated in one document only"
            sources = filled
        elif sources:
            status, confidence, reason = "blank", "none", "left blank in the document"
        else:
            status, confidence, reason = "missing", "none", "not found in any document"

        entry = {"id": field["id"], "label": field["label"], "importance": field["importance"],
                 "status": status, "confidence": confidence, "reason": reason, "sources": sources}
        if status == "missing":
            entry["possible_mentions"] = _possible_mentions(documents, field["hints"])
        if status != "found" and field["importance"] == "required":
            questions.append(f"Please provide: {field['label']}")
        fields.append(entry)

    for it in contradictions["items"]:
        if it["severity"] == "high":
            where = ", ".join(s["chunk_id"] for s in it["sides"])
            questions.append(f"Resolve conflict: {it['topic']} ({where})")

    required = [f for f in fields if f["importance"] == "required"]
    found_required = sum(f["status"] == "found" for f in required)
    high_conflicts = sum(it["severity"] == "high" for it in contradictions["items"])
    ready = found_required == len(required) and high_conflicts == 0

    return {
        "draft_type": draft_type,
        "label": spec["label"],
        "readiness": {
            "required_total": len(required),
            "required_found": found_required,
            "percent": round(100 * found_required / len(required)) if required else 100,
            "status": ("Ready to draft" if ready else
                       "Draft with gaps: missing parts will be marked [information needed]"),
        },
        "fields": fields,
        "questions": questions,
        "unverified_extractions": [
            {"doc_id": d["doc_id"], "keys": d["unverified_facts"]}
            for d in documents if d.get("unverified_facts")
        ],
    }


# ---------- entry points used by app.py ----------

def analyze_case(draft_type=DEFAULT_DRAFT_TYPE):
    if draft_type not in DRAFT_TYPES:
        raise ValueError(f"Unknown draft type: {draft_type}")
    store = storage.load_store()
    documents = store["documents"]
    if not documents:
        raise ValueError("Upload at least one document first.")

    doc_ids = [d["doc_id"] for d in documents]
    contradictions = find_contradictions(documents)
    missing = missing_info_report(documents, draft_type, contradictions)

    stamp = datetime.now().isoformat(timespec="seconds")
    for part in (contradictions, missing):
        part["analyzed_at"] = stamp
        part["doc_ids"] = doc_ids

    saved = storage.save_outputs(doc_ids, missing_info=missing, contradictions=contradictions)
    return {"missing_info": missing, "contradictions": contradictions, "saved": saved}


def draft_type_list():
    return [{"id": k, "label": v["label"]} for k, v in DRAFT_TYPES.items()]
