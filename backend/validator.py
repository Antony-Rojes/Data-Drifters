"""Feature 4: citation and claim validator. Pure Python, no Gemini.

For every sentence of a draft or answer it checks:
  1. Citations: the chunk ID exists in store.json AND the quote is really inside that chunk.
     (If the ID is wrong but the quote exists in another chunk, the citation is corrected.)
  2. Claim support: every "critical token" in the sentence (names, numbers, dates, section
     numbers, Acts/statutes, case-law markers) appears in the cited source text.
  3. Template sentences (legal wording such as the prayer) may not contain ANY critical token
     or factual statement. If they do, they need a citation like a fact.
Failures: a fact sentence is replaced by "[information needed: ...]"; a template sentence is removed.
Abstain over guess.
"""
import re

MISSING_TAG = "[information needed"
MIN_QUOTE_CHARS = 8
MAX_QUOTE_CHARS = 400

# Capitalised words that are normal legal/English words, not names. Everything else that is
# capitalised (a person, place, statute acronym...) must be found in the sources.
COMMON = set("""
a about above accordance accused act action address addressed adhere advocate affidavit affirm aforesaid
after again against age all allow allowed also am an and annexure any appear appearance appeared applicant
application apply appropriate april are as aside at august authority bail be been before behalf being
belief believe best bond both brief but by can case cases cause central certain charge chief circumstances
client co code concealed condition conditions consider considered contd contents copy correct counsel court
courts criminal cum custody date dated day days dear december declare deemed deponent detail details
district do documents does dr due during each earlier evidence ex except facts factual false february
first fit following for from further given government grant granted grounds had has have he hearing
held hence her hereby herein hereunder high him his hon'ble honble honour honourable however humble i if
in indian information instant investigation investigating is it its january judge judicial july june
just justice kindly kumari knowledge law laws learned legal liberty ld lordship lordships madam magistrate
march matter may me mentioned miss mo month months monday more most mr mrs ms my name named nature
needed nephew niece no not nothing notice november now number october of offence officer on one or order
orders other others our out page para paragraph part parties party pass passed penal per person persons
petition petitioner petitioners place please police post pray prayed prayer present presented prima
procedure proper provisions public reasonable reasons record ref regard regarding regards relative
relevant republic residence respectfully respondent respondents rs rupees said saturday section sections
see senior september session sessions shall she sheweth shri signature signed sir smt so solemnly some
sri state statement statements station submit submitted subject such sunday surety sureties sworn
than thank that the their them then there therefore therein these they this those thursday through
to trial true truly tuesday two under undersigned undertake undertakes upon us versus verification
verified verify vs we wednesday whatever whereas wherefore which who whom will with within without
witness witnesses yours your fir pin po gd pw dw
""".split())

# Field labels and normal sentence starters (a sentence often starts with a capital letter).
COMMON |= set("""
accordingly according additionally addresses admittedly agency allegation allegations already although
amount another answer apart applications arrest arrested aged based because besides being both chargesheet
complaint consequently conflict confirmed currently defence demand deadline deponent detained documents
document even every father finally firstly further having health here husband incident lastly likewise
many moreover mother name names neither nor note notably occupation occurrence offences once only
orders passage personal previous prior prosecution rather recipient recovery release released relation
relationship remand resolve secondly sender sheet signing similarly since sources source specifically
status thereafter thirdly though thus till unless until whereby whether while why yes age address
custody surrender instead also hence each where when what how jail liberty bond surety records
subsequently furthermore meanwhile initially ultimately immediately notwithstanding pursuant concerning
regarding inasmuch whereupon thereupon incidentally apparently allegedly reportedly evidently
appellant victim deceased informant complainant convict respondent petitioner prosecutrix investigator
medical hospital doctor patient injury injuries treatment clinic vehicle car truck
panchnama challan chalan malkhana thana rojnamcha roknama supurdari daroga vakalatnama tahrir parcha fir
""".split())

STATUTE_WORDS = set("""bharatiya nyaya sanhita nagarik suraksha sakshya adhiniyam constitution narcotic
drugs psychotropic substances negotiable instruments technology protection children sexual offences
dowry prohibition arms atrocities laundering corruption""".split())
COMMON |= STATUTE_WORDS

# Laws: a mention in the draft is supported if ANY form of the same law appears in the sources.
STATUTES = {
    "IPC": [r"indian penal code", r"\bipc\b"],
    "CrPC": [r"code of criminal procedure", r"criminal procedure code", r"\bcrpc\b"],
    "BNS": [r"bharatiya nyaya sanhita", r"\bbns\b"],
    "BNSS": [r"bharatiya nagarik suraksha sanhita", r"\bbnss\b"],
    "BSA": [r"bharatiya sakshya adhiniyam", r"\bbsa\b"],
    "Evidence Act": [r"evidence act", r"\biea\b"],
    "NDPS Act": [r"narcotic drugs and psychotropic", r"\bndps\b"],
    "NI Act": [r"negotiable instruments act", r"\bni act\b"],
    "IT Act": [r"information technology act", r"\bit act\b"],
    "POCSO Act": [r"protection of children from sexual offences", r"\bpocso\b"],
    "Dowry Prohibition Act": [r"dowry prohibition act"],
    "Arms Act": [r"arms act"],
    "UAPA": [r"unlawful activities", r"\buapa\b"],
    "PMLA": [r"prevention of money laundering", r"\bpmla\b"],
    "MV Act": [r"motor vehicles act", r"\bmv act\b"],
    "SC/ST Act": [r"scheduled castes and scheduled tribes", r"\bsc/?st act\b", r"prevention of atrocities"],
    "Domestic Violence Act": [r"protection of women from domestic violence", r"domestic violence act", r"\bdv act\b", r"\bpwdva\b"],
    "Prevention of Corruption Act": [r"prevention of corruption", r"\bpc act\b"],
    "Constitution": [r"constitution of india", r"\bconstitution\b", r"\barticle \d+"],
}
_STATUTE_ACRONYMS = {"ipc", "crpc", "bns", "bnss", "bsa", "iea", "ndps", "pocso", "uapa", "pmla", "pwdva"}

# Month name to number mapping for date normalisation.
MONTH_MAP = {
    "january": "1", "february": "2", "march": "3", "april": "4",
    "may": "5", "june": "6", "july": "7", "august": "8",
    "september": "9", "october": "10", "november": "11", "december": "12",
    "jan": "1", "feb": "2", "mar": "3", "apr": "4", "jun": "6",
    "jul": "7", "aug": "8", "sep": "9", "sept": "9", "oct": "10",
    "nov": "11", "dec": "12"
}

# Allow-list of legal boilerplate and prayer formulas that need no factual citation.
TEMPLATE_FORMULAS = re.compile(
    r"\b(pray\w*|prayer|craves?\s+leave|liberty\s+to|grant\s+bail|interim\s+bail|"
    r"be\s+pleased\s+to|pass\s+such\s+other\s+order|just\s+and\s+proper|"
    r"equity\s+and\s+justice|meet\s+the\s+ends\s+of\s+justice|"
    r"undertak\w*|abide\s+by|terms\s+and\s+conditions|cooperat\w*\s+with|"
    r"not\s+tamper|not\s+flee|not\s+influence|available\s+for\s+investigation|"
    r"join\s+investigation|furnish\s+surety|attend\s+the\s+court|"
    r"solemnly\s+affirm\w*|verified\s+at|contents\s+of\s+paragraph\w*|"
    r"true\s+to\s+my\s+knowledge|true\s+to\s+best\s+of|belief\s+and\s+information|"
    r"deponent|sworn\s+before\s+me|most\s+respectfully\s+sheweth|"
    r"respectfully\s+submitted|in\s+the\s+court\s+of|application\s+on\s+behalf\s+of|"
    r"may\s+it\s+please\s+your\s+honour|and\s+for\s+this\s+act\s+of\s+kindness|"
    r"shall\s+ever\s+pray|court\s+deems?\s+fit|interest\s+of\s+justice|"
    r"ad\s+interim|relief\s+sought|bona\s+fide)\b",
    re.IGNORECASE,
)

# Words that make a sentence a factual statement about the case (needs a citation).
FACT_WORDS = re.compile(
    r"\b(arrest\w*|custody|innocen\w*|antecedent\w*|criminal record|implicat\w*|resid\w*|employ\w*|"
    r"aged|years old|married|wife|husband|son of|daughter|father|mother|born|health|ill|illness|"
    r"injur\w*|paid|amount|absconding|abscond|surrender\w*|recover\w*|seiz\w*|complain\w*|alleg\w*|"
    r"occurred|incident|fir|chargesheet|charge sheet|investigat\w*|previous|earlier|rejected|"
    r"pending|stolen|theft|assault\w*|threat\w*|dowry|cruelty|relationship|nephew|friend|retired)\b",
    re.IGNORECASE)


# ---------- text normalisation ----------

def canon(text):
    """Lower-case, same quotes/dashes, single spaces. Used for quote matching."""
    text = (text or "").replace("\u00a0", " ")
    text = re.sub(r"[\u2018\u2019\u201b`]", "'", text)
    text = re.sub(r"[\u201c\u201d\u201f]", '"', text)
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _squash_acronyms(text):
    # "Cr.P.C." -> "CrPC", "I.P.C." -> "IPC", "P.S." -> "PS"
    return re.sub(r"\b((?:[A-Za-z]{1,3}\.){2,})", lambda m: m.group(1).replace(".", ""), text or "")


def _norm_number(token):
    token = re.sub(r"^(\d+)(st|nd|rd|th)$", r"\1", token.lower())
    return str(int(token)) if token.isdigit() else token


def source_tokens(text):
    """Set of normalised words and derived numbers (months, ordinals) of a source text."""
    words = re.findall(r"[a-z0-9]+", _squash_acronyms(text).lower())
    tokens = {_norm_number(w) for w in words}
    for w in words:
        if w in MONTH_MAP:
            tokens.add(MONTH_MAP[w])
    return tokens


def _squashed(text):
    return re.sub(r"[^a-z0-9]", "", _squash_acronyms(text).lower())


def _strip_markers(text):
    text = re.sub(r"\[information needed[^\]]*\]", " ", text or "", flags=re.IGNORECASE)
    return re.sub(r"^\s*\(?([0-9]{1,2}|[ivxlc]{1,5}|[a-h])[.)]\s+", "", text, flags=re.IGNORECASE)


strip_markers = _strip_markers  # public name, used by the evaluation


def critical_tokens(text):
    """Names, numbers, dates, sections, acronyms and statutes that must be backed by a source."""
    text = _squash_acronyms(_strip_markers(text))
    tokens = []
    for raw in re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?", text):
        word = re.sub(r"'s$", "", raw)
        low = word.lower()
        if any(ch.isdigit() for ch in word):
            tokens.append(("number", _norm_number(low)))
        elif word[0].isupper() and len(word) >= 2 and low not in COMMON and low not in _STATUTE_ACRONYMS:
            if low.endswith("ly") and len(low) > 3:
                continue
            tokens.append(("name", low))
    low_text = text.lower()
    for law, patterns in STATUTES.items():
        if any(re.search(p, low_text) for p in patterns):
            tokens.append(("law", law))
    seen, unique = set(), []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def _law_supported(law, source_text):
    """Checks law references using strict word boundaries and acronym handling on spaced text."""
    norm_source = _squash_acronyms(source_text or "")
    for p in STATUTES.get(law, []):
        if re.search(p, norm_source, flags=re.IGNORECASE):
            return True
    return False


def unsupported_tokens(text, source_text):
    """Critical tokens of `text` that do not appear in `source_text`."""
    words = source_tokens(source_text)
    missing = []
    for kind, value in critical_tokens(text):
        ok = _law_supported(value, source_text) if kind == "law" else value in words
        if not ok:
            missing.append(value)
    return missing


def is_template(text):
    """True if the sentence matches the allow-list of standard legal boilerplate formulas."""
    stripped = _strip_markers(text)
    return bool(TEMPLATE_FORMULAS.search(stripped))


def is_factual(text):
    """A sentence is treated as a factual claim needing citation unless it is a pure gap
    marker or matches the allow-list of legal formula templates (with no critical tokens)."""
    if critical_tokens(text):
        return True
    if MISSING_TAG in (text or "").lower():
        return False
    if is_template(text):
        return False
    return True


def has_negation(text):
    """Detects genuine negations (not, never, nil, neither, nor, none, n't, no),
    excluding 'No.' as an abbreviation for numbers (e.g. 'FIR No. 123', 'Case No.')."""
    clean = re.sub(
        r"\b(fir|case|cc|rc|mlc|serial|sl|item|flat|house|plot|page|para|paragraph|cr)\s*no\.?\s*\d*",
        "",
        text or "",
        flags=re.IGNORECASE,
    )
    clean = re.sub(r"\bno\.\s*\d*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bno\s*[\.:#]\s*\d*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bno\s+\d+\b", "", clean, flags=re.IGNORECASE)
    return bool(re.search(r"\b(not|never|nil|neither|nor|none|n't)\b|\bno\b(?!\s*[\.:#\d])", clean, re.IGNORECASE))


# ---------- citation check ----------

def _quote_parts(quote):
    # Gemini sometimes shortens a quote with "..." - every part must still be real text.
    return [p.strip() for p in re.split(r"\.\.\.|\u2026", quote) if p.strip()]


def _contains_in_order(chunk_text, parts, max_gap=250):
    """Checks that all parts of a quote appear in sequential order within the chunk,
    with no more than max_gap characters between adjacent parts."""
    text = canon(chunk_text)
    pos = 0
    for i, p in enumerate(parts):
        p_can = canon(p)
        idx = text.find(p_can, pos)
        if idx == -1:
            return False
        if i > 0 and (idx - pos) > max_gap:
            return False
        pos = idx + len(p_can)
    return True


def check_citation(citation, by_id, chunks):
    """Returns (verified_citation or None, note)."""
    quote = str(citation.get("quote") or "").strip().strip('"').strip()
    claimed = str(citation.get("chunk_id") or "").strip()
    parts = _quote_parts(quote)
    if not parts or len(canon(quote)) < MIN_QUOTE_CHARS or len(quote) > MAX_QUOTE_CHARS:
        return None, "quote missing, too short or too long"

    # For composite quotes with ellipses, require each piece to be at least 3 words
    if len(parts) > 1:
        for p in parts:
            if len(re.findall(r"[a-z0-9]+", p.lower())) < 3:
                return None, "quote pieces separated by ellipses must be at least 3 words"

    def contains(chunk):
        return _contains_in_order(chunk["text"], parts)

    if claimed in by_id and contains(by_id[claimed]):
        return {"chunk_id": claimed, "quote": quote}, "ok"
    for c in chunks:
        if contains(c):
            return {"chunk_id": c["chunk_id"], "quote": quote}, f"chunk ID corrected from {claimed or 'none'}"
    if claimed not in by_id:
        return None, f"chunk {claimed or '(none)'} does not exist"
    return None, f"quote not found in {claimed}"


# ---------- main validation ----------

def _placeholder(label):
    return f"[information needed: {label}]"


def validate_sentences(sentences, chunks):
    """sentences: [{"text", "type": fact|template|missing, "citations": [{"chunk_id","quote"}]}]
    Returns (validated_sentences, removed, stats)."""
    by_id = {c["chunk_id"]: c for c in chunks}
    out, removed = [], []
    stats = {"sentences": 0, "fact_claims": 0, "verified": 0, "repaired": 0, "replaced": 0,
             "removed": 0, "template": 0, "missing": 0, "citations_total": 0,
             "citations_verified": 0, "citations_corrected": 0, "citations_invalid": 0,
             "unsupported_tokens": []}

    for s in sentences or []:
        if not isinstance(s, dict):
            continue
        text = re.sub(r"\s+", " ", str(s.get("text") or "")).strip()
        if not text:
            continue
        stats["sentences"] += 1
        kind = str(s.get("type") or "fact").lower()
        citations = s.get("citations") or []
        if not isinstance(citations, list):
            citations = []

        good, issues = [], []
        for cit in citations:
            if not isinstance(cit, dict):
                continue
            stats["citations_total"] += 1
            verified, note = check_citation(cit, by_id, chunks)
            if verified:
                if verified not in good:
                    good.append(verified)
                stats["citations_verified"] += 1
                if note != "ok":
                    stats["citations_corrected"] += 1
                    issues.append(note)
            else:
                stats["citations_invalid"] += 1
                issues.append(f"citation removed: {note}")

        has_missing_tag = MISSING_TAG in text.lower()
        factual = is_factual(text)

        # Pure gap marker or wording with no facts in it.
        if not factual:
            if has_missing_tag or kind == "missing":
                stats["missing"] += 1
                if not has_missing_tag:
                    text = _placeholder(text.rstrip("."))
                out.append({"text": text, "type": "missing", "citations": [], "status": "missing", "issues": issues})
            else:
                stats["template"] += 1
                out.append({"text": text, "type": "template", "citations": good, "status": "template", "issues": issues})
            continue

        # Everything else is a factual claim and must be backed by a verified citation.
        stats["fact_claims"] += 1
        cited_text = " ".join(by_id[c["chunk_id"]]["text"] for c in good)
        missing_tokens = unsupported_tokens(text, cited_text) if good else [v for _, v in critical_tokens(text)]
        neg_mismatch = bool(good and has_negation(text) != has_negation(cited_text))

        if good and not missing_tokens and not neg_mismatch:
            status = "repaired" if issues else "verified"
            stats[status] += 1
            out.append({"text": text, "type": "missing" if has_missing_tag else "fact",
                        "citations": good, "status": status, "issues": issues})
            continue

        if not good:
            reason = "no verified citation"
        elif missing_tokens:
            reason = "not supported by the cited source: " + ", ".join(missing_tokens[:6])
        else:
            reason = "negation mismatch between claim and cited source"

        stats["unsupported_tokens"] += missing_tokens
        record = {"original_text": text, "type": kind, "reason": reason, "issues": issues}
        if kind == "template":
            stats["removed"] += 1
            removed.append(record)
        else:
            stats["replaced"] += 1
            removed.append(record)
            out.append({"text": _placeholder("verified source for this statement"), "type": "missing",
                        "citations": [], "status": "replaced", "issues": [reason] + issues,
                        "original_text": text})

    claims = stats["fact_claims"]
    passed = stats["verified"] + stats["repaired"]
    stats["groundedness_before_pct"] = round(100 * passed / claims, 1) if claims else 100.0
    stats["groundedness_after_pct"] = 100.0  # by construction: unsupported claims were removed
    stats["unsupported_tokens"] = sorted(set(stats["unsupported_tokens"]))
    stats["fabrications_left"] = len(audit(out, chunks))
    return out, removed, stats


def audit(sentences, chunks):
    """Independent final check: lists any sentence in the OUTPUT that is still not verifiable.
    Must return [] for every validated draft or answer (the zero-fabrication gate)."""
    by_id = {c["chunk_id"]: c for c in chunks}
    problems = []
    for s in sentences or []:
        if not isinstance(s, dict):
            continue
        text = s.get("text", "")
        cits = s.get("citations") or []
        for c in cits:
            if not isinstance(c, dict):
                continue
            chunk = by_id.get(c.get("chunk_id"))
            parts = _quote_parts(c.get("quote", ""))
            if not parts or not chunk or not _contains_in_order(chunk["text"], parts) or (
                len(parts) > 1 and any(len(re.findall(r"[a-z0-9]+", p.lower())) < 3 for p in parts)
            ):
                problems.append({"text": text, "problem": f"bad citation {c.get('chunk_id')}"})
        if is_factual(text):
            if not cits:
                problems.append({"text": text, "problem": "factual sentence without citation"})
                continue
            valid_cits = [c for c in cits if isinstance(c, dict) and c.get("chunk_id") in by_id]
            cited = " ".join(by_id[c["chunk_id"]]["text"] for c in valid_cits)
            bad = unsupported_tokens(text, cited)
            if bad:
                problems.append({"text": text, "problem": "unsupported: " + ", ".join(bad)})
            elif has_negation(text) != has_negation(cited):
                problems.append({"text": text, "problem": "negation mismatch with cited source"})
    return problems


def validate_draft(sections, chunks):
    """sections: [{"id","heading","sentences":[...]}]. Validates every section."""
    all_removed, totals, out_sections = [], None, []
    for sec in sections:
        sentences, removed, stats = validate_sentences(sec.get("sentences"), chunks)
        for r in removed:
            r["section"] = sec.get("heading", sec.get("id"))
        all_removed += removed
        out_sections.append({"id": sec.get("id"), "heading": sec.get("heading"), "sentences": sentences})
        if totals is None:
            totals = dict(stats)
        else:
            for k, v in stats.items():
                if isinstance(v, (int, float)) and not k.endswith("_pct"):
                    totals[k] += v
                elif isinstance(v, list):
                    totals[k] = sorted(set(totals[k]) | set(v))
    totals = totals or validate_sentences([], chunks)[2]
    claims = totals["fact_claims"]
    totals["groundedness_before_pct"] = round(
        100 * (totals["verified"] + totals["repaired"]) / claims, 1) if claims else 100.0
    totals["groundedness_after_pct"] = 100.0
    totals["fabrications_left"] = sum(len(audit(s["sentences"], chunks)) for s in out_sections)
    return out_sections, all_removed, totals
