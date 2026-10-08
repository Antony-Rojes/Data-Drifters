"""Evaluation: baseline vs our system, with ablations.

  python eval/run_eval.py                    all cases (dev + heldout)
  python eval/run_eval.py --split heldout    only held-out cases
  python eval/run_eval.py --skip-drafts      questions + retrieval only (fewer Gemini calls)
  python eval/run_eval.py --pause 4          wait 4 s between Gemini-heavy steps (free-tier limits)

It uses its own store (eval/results/_eval_store.json), so your dashboard case is not touched.
Outputs: eval/results/results.md (tables for the write-up), results.json (everything),
         usefulness_sheet.csv (rate usefulness 1-5 by hand).

Systems compared
  baseline            plain Gemini, full document text, no chunk IDs, no validator
  ours_no_validator   retrieval + grounded JSON prompt, raw Gemini output (ablation: validator off)
  ours_full           retrieval + grounded prompt + Python validator (the real system)
  ours_no_retrieval   all chunks + grounded prompt + validator (ablation: retrieval off)

Metrics (the same scorer for every system)
  groundedness %      factual sentences traceable to a real passage: all names/numbers/dates/sections
                      of the sentence appear in one or two passages that share >= 50% of its content words
  fabrications        factual sentences with a name/number/date/law that appears NOWHERE in the case,
                      plus citations whose quote is not in any passage (must be 0 for ours_full)
  answer accuracy     expected strings found in the answer (answerable questions)
  abstention          for unanswerable questions: says information is missing and invents nothing
  retrieval           recall@5, hit@5 and MRR@10 of the gold passages, per retrieval mode
"""
import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import analyzer, config, drafter, extractor, qa, retrieval, storage, validator  # noqa: E402
from eval import baseline  # noqa: E402

EVAL_DIR = ROOT / "eval"
RESULTS = EVAL_DIR / "results"
DOC_CACHE = RESULTS / "doc_cache"
SYSTEMS = ["baseline", "ours_no_validator", "ours_full", "ours_no_retrieval"]
ABSTAIN_PHRASES = ["information needed", "not mentioned", "not stated", "does not mention", "do not mention",
                   "no information", "not available", "not specified", "does not contain", "do not contain",
                   "not provided", "not found", "no mention", "cannot be determined", "not in the documents"]


# ---------- isolated store ----------

def use_eval_store():
    RESULTS.mkdir(parents=True, exist_ok=True)
    DOC_CACHE.mkdir(parents=True, exist_ok=True)
    config.CACHE_DIR = RESULTS
    config.STORE_PATH = RESULTS / "_eval_store.json"
    config.ARCHIVE_DIR = RESULTS / "_archive"
    config.ARCHIVE_DIR.mkdir(exist_ok=True)


def load_case(case):
    """Fresh store with the case documents. Extraction results are cached to save Gemini calls."""
    storage.reset_store()
    for rel in case["documents"]:
        path = EVAL_DIR / rel
        if not path.exists():
            raise FileNotFoundError(f"Missing document: {path}")
        sha = extractor.file_hash(path)
        doc_id = storage.reserve_doc_id()
        cache = DOC_CACHE / f"{sha[:16]}_{doc_id}.json"
        if cache.exists():
            doc = json.loads(cache.read_text(encoding="utf-8"))
        else:
            doc = extractor.process_pdf(path, doc_id, path.name, sha)
            cache.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        storage.add_document(doc)
    return storage.load_store()["documents"]


# ---------- scoring helpers ----------

def squash(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


# Words that talk ABOUT the documents, not about the case. Ignored for every system.
META_WORDS = {"document", "documents", "another", "say", "says", "state", "states", "stat", "record", "recorded",
              "mention", "mentioned", "accord", "according", "source", "also", "per", "both", "however"}


def content_words(text):
    text = validator.strip_markers(text)
    return {w for w in retrieval.tokenize(text) if len(w) >= 3 and not w.isdigit() and w not in META_WORDS}


def split_sentences(text):
    """Plain text -> sentences (for the baseline, which has no structure)."""
    text = re.sub(r"[*#>`_]+", " ", text or "")
    out = []
    for line in text.splitlines():
        line = re.sub(r"^\s*[-\u2022]\s*", "", line).strip()
        if not line:
            continue
        pieces = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(\[\"])", line)
        merged = []
        for piece in pieces:
            last = merged[-1].split()[-1] if merged and merged[-1].split() else ""
            # do not split after abbreviations like "No.", "Ld.", "P.S.", "Rs."
            if merged and (len(last) <= 4 and last.endswith(".") or re.search(r"\w\.\w", last)):
                merged[-1] += " " + piece
            else:
                merged.append(piece)
        out += [m.strip() for m in merged if m.strip()]
    return [{"text": s, "citations": None} for s in out]


def traceable(text, chunks):
    """True if one passage, or two passages together, back every critical token and >= 50% of words."""
    words = content_words(text)
    crit = validator.critical_tokens(text)

    def rank(c):  # passages that contain the sentence's names/numbers first, then shared words
        missing = len(validator.unsupported_tokens(text, c["text"])) if crit else 0
        return (len(crit) - missing, len(words & content_words(c["text"])))

    scored = sorted(chunks, key=rank, reverse=True)[:6]
    candidates = [[c] for c in scored] + [[a, b] for i, a in enumerate(scored) for b in scored[i + 1:]]
    for group in candidates:
        joined = " ".join(c["text"] for c in group)
        if validator.unsupported_tokens(text, joined):
            continue
        if not words or len(words & content_words(joined)) / len(words) >= 0.5:
            return True
    return False


def score_output(sentences, chunks, cited):
    """Same scorer for all systems. sentences: [{"text", "citations": [...] or None}]."""
    by_id = {c["chunk_id"]: c for c in chunks}
    all_text = " ".join(c["text"] for c in chunks)
    m = {"claims": 0, "grounded": 0, "fabricated_claims": 0, "fabricated_citations": 0,
         "citations": 0, "abstained": False, "fabricated_examples": []}
    for s in sentences:
        text = str(s.get("text") or "").strip()
        if not text:
            continue
        low = text.lower()
        if any(p in low for p in ABSTAIN_PHRASES):
            m["abstained"] = True
            if validator.MISSING_TAG in low and not validator.critical_tokens(text):
                continue
        if not validator.is_factual(text):
            continue
        m["claims"] += 1
        if traceable(text, chunks):
            m["grounded"] += 1
        bad = validator.unsupported_tokens(text, all_text)
        if bad:
            m["fabricated_claims"] += 1
            m["fabricated_examples"].append({"text": text[:200], "not_in_sources": bad[:6]})
        if cited:
            for c in s.get("citations") or []:
                m["citations"] += 1
                ok, _ = validator.check_citation(c, by_id, chunks)
                if not ok:
                    m["fabricated_citations"] += 1
                    m["fabricated_examples"].append({"text": text[:200], "bad_citation": c.get("chunk_id")})
    return m


def answer_checks(query, sentences, m):
    text = " ".join(str(s.get("text") or "") for s in sentences)
    result = {}
    if query.get("expect_abstain"):
        result["abstain_ok"] = m["abstained"] and m["fabricated_claims"] == 0
    if query.get("answer_contains"):
        result["accurate"] = all(squash(x) in squash(text) for x in query["answer_contains"])
    elif query.get("answer_contains_any"):
        result["accurate"] = any(squash(x) in squash(text) for x in query["answer_contains_any"])
    return result


def plain(sentences):
    return [{"text": s.get("text", ""), "citations": s.get("citations")} for s in sentences]


def draft_sentences(sections):
    return [s for sec in sections for s in sec["sentences"]]


# ---------- the three evaluations ----------

def eval_retrieval(case, chunks, pause):
    rows = []
    for q in case["queries"]:
        gold = [g for g in q.get("gold_quotes", [])]
        if not gold:
            continue
        relevant = {c["chunk_id"] for c in chunks if any(validator.canon(g) in validator.canon(c["text"]) for g in gold)}
        if not relevant:
            print(f"  ! {q['id']}: no passage contains the gold quote, check queries.json")
            continue
        row = {"id": q["id"], "relevant": sorted(relevant)}
        for mode in retrieval.MODES:
            out = retrieval.retrieve(q["query"], k=10, mode=mode)
            ids = [r["chunk_id"] for r in out["results"]]
            first = next((n for n, i in enumerate(ids, start=1) if i in relevant), None)
            row[mode] = {"recall@5": len(relevant & set(ids[:5])) / len(relevant),
                         "hit@5": 1.0 if relevant & set(ids[:5]) else 0.0,
                         "mrr@10": 1.0 / first if first else 0.0,
                         "mode_used": out["mode_used"], "top5": ids[:5]}
        rows.append(row)
        time.sleep(pause)
    return rows


def eval_questions(case, documents, chunks, pause):
    rows = []
    for q in case["queries"]:
        print(f"  question {q['id']}: {q['query']}")
        row = {"id": q["id"], "query": q["query"], "systems": {}}
        outputs = {}
        try:
            outputs["baseline"] = (split_sentences(baseline.answer(q["query"], documents)), False)
        except Exception as e:
            print(f"    baseline failed: {e}")
        try:
            full = qa.answer(q["query"])
            outputs["ours_no_validator"] = (plain(full["raw_sentences"]), True)
            outputs["ours_full"] = (plain(full["sentences"]), True)
        except Exception as e:
            print(f"    ours failed: {e}")
        try:
            nr = qa.answer(q["query"], use_retrieval=False)
            outputs["ours_no_retrieval"] = (plain(nr["sentences"]), True)
        except Exception as e:
            print(f"    no-retrieval failed: {e}")
        for name, (sentences, cited) in outputs.items():
            m = score_output(sentences, chunks, cited)
            m.update(answer_checks(q, sentences, m))
            m["output"] = " ".join(str(s.get("text") or "") for s in sentences)[:1500]
            row["systems"][name] = m
        rows.append(row)
        time.sleep(pause)
    return rows


def eval_drafts(case, documents, chunks, pause):
    rows = []
    for draft_type in case.get("drafts", []):
        print(f"  draft: {draft_type}")
        label = analyzer.DRAFT_TYPES[draft_type]["label"]
        report = analyzer.missing_info_report(documents, draft_type, {"items": []})
        found_values = [s["value"] for f in report["fields"] if f["status"] == "found" for s in f["sources"]]
        row = {"draft_type": draft_type, "systems": {}}
        outputs = {}
        try:
            outputs["baseline"] = (split_sentences(baseline.draft(label, documents)), False)
        except Exception as e:
            print(f"    baseline failed: {e}")
        try:
            full = drafter.draft(draft_type, save=False)
            outputs["ours_no_validator"] = (plain(draft_sentences(full["raw_sections"])), True)
            outputs["ours_full"] = (plain(draft_sentences(full["sections"])), True)
            row["ours_source"] = full["source"]
        except Exception as e:
            print(f"    ours failed: {e}")
        try:
            nr = drafter.draft(draft_type, use_retrieval=False, save=False)
            outputs["ours_no_retrieval"] = (plain(draft_sentences(nr["sections"])), True)
        except Exception as e:
            print(f"    no-retrieval failed: {e}")
        for name, (sentences, cited) in outputs.items():
            m = score_output(sentences, chunks, cited)
            text = " ".join(str(s.get("text") or "") for s in sentences)
            covered = [v for v in found_values if squash(v) and squash(v) in squash(text)]
            m["coverage_pct"] = round(100 * len(covered) / len(found_values), 1) if found_values else None
            m["gaps_marked"] = text.lower().count(validator.MISSING_TAG)
            m["output"] = text[:4000]
            row["systems"][name] = m
        rows.append(row)
        time.sleep(pause)
    return rows


def eval_contradictions(case, documents):
    expected = case.get("expected_contradictions")
    if not expected:
        return None
    report = analyzer.find_contradictions(documents)
    quotes = " ".join(s["quote"] for it in report["items"] for s in it["sides"])
    return {"expected": expected, "found_items": len(report["items"]),
            "detected": all(squash(x) in squash(quotes) for x in expected),
            "checked_by": report["checked_by"], "gemini_error": report["gemini_error"]}


# ---------- aggregation and report ----------

def pct(a, b):
    return round(100 * a / b, 1) if b else None


def aggregate(rows):
    agg = {}
    for name in SYSTEMS:
        ms = [r["systems"][name] for r in rows if name in r["systems"]]
        if not ms:
            continue
        acc = [m["accurate"] for m in ms if "accurate" in m]
        abst = [m["abstain_ok"] for m in ms if "abstain_ok" in m]
        claims = sum(m["claims"] for m in ms)
        agg[name] = {
            "items": len(ms), "claims": claims, "grounded": sum(m["grounded"] for m in ms),
            "groundedness_pct": pct(sum(m["grounded"] for m in ms), claims),
            "fabricated_claims": sum(m["fabricated_claims"] for m in ms),
            "fabricated_citations": sum(m["fabricated_citations"] for m in ms),
            "accuracy_pct": pct(sum(acc), len(acc)), "abstention_pct": pct(sum(abst), len(abst)),
        }
        cov = [m["coverage_pct"] for m in ms if m.get("coverage_pct") is not None]
        if cov:
            agg[name]["coverage_pct"] = round(sum(cov) / len(cov), 1)
    return agg


def aggregate_retrieval(rows):
    out = {}
    for mode in retrieval.MODES:
        vals = [r[mode] for r in rows if mode in r]
        if vals:
            out[mode] = {k: round(sum(v[k] for v in vals) / len(vals), 3) for k in ("recall@5", "hit@5", "mrr@10")}
            out[mode]["queries"] = len(vals)
    return out


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join("-" if v is None else str(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def write_report(all_results, split):
    qa_rows = [r for c in all_results for r in c["questions"]]
    dr_rows = [r for c in all_results for r in c["drafts"]]
    rt_rows = [r for c in all_results for r in c["retrieval"]]
    qa_agg, dr_agg, rt_agg = aggregate(qa_rows), aggregate(dr_rows), aggregate_retrieval(rt_rows)

    md = [f"# Evaluation results ({split})", "",
          f"Run: {datetime.now().isoformat(timespec='seconds')}. Cases: "
          + ", ".join(f"{c['case_id']} ({c['split']})" for c in all_results), ""]
    md += ["## Questions (RAG chat)", "", table(
        ["System", "Questions", "Claims", "Groundedness %", "Fabricated claims", "Fabricated citations",
         "Answer accuracy %", "Correct abstention %"],
        [[n, a["items"], a["claims"], a["groundedness_pct"], a["fabricated_claims"], a["fabricated_citations"],
          a["accuracy_pct"], a["abstention_pct"]] for n, a in qa_agg.items()]), ""]
    if dr_agg:
        md += ["## Drafts", "", table(
            ["System", "Drafts", "Claims", "Groundedness %", "Fabricated claims", "Fabricated citations",
             "Fact coverage %"],
            [[n, a["items"], a["claims"], a["groundedness_pct"], a["fabricated_claims"], a["fabricated_citations"],
              a.get("coverage_pct")] for n, a in dr_agg.items()]), ""]
    md += ["## Retrieval (gold passages)", "", table(
        ["Mode", "Queries", "Recall@5", "Hit@5", "MRR@10"],
        [[mode, a["queries"], a["recall@5"], a["hit@5"], a["mrr@10"]] for mode, a in rt_agg.items()]), ""]
    contra = [c for c in all_results if c.get("contradictions")]
    if contra:
        md += ["## Contradiction detection", "", table(
            ["Case", "Expected conflict", "Detected", "Items found", "Checked by"],
            [[c["case_id"], " vs ".join(c["contradictions"]["expected"]), c["contradictions"]["detected"],
              c["contradictions"]["found_items"], "+".join(c["contradictions"]["checked_by"])] for c in contra]), ""]

    full = [a for a in (qa_agg.get("ours_full"), dr_agg.get("ours_full")) if a]
    fabrications = sum(a["fabricated_claims"] + a["fabricated_citations"] for a in full)
    md += ["## Zero-fabrication gate", "",
           f"ours_full fabricated claims + citations: **{fabrications}**. "
           + ("PASS" if fabrications == 0 else "FAIL: read results.json -> fabricated_examples"), ""]
    examples = [(r.get("id") or r.get("draft_type"), n, ex) for r in qa_rows + dr_rows
                for n, m in r["systems"].items() for ex in m["fabricated_examples"][:2]]
    if examples:
        md += ["## Examples of fabrications caught (first 10)", ""]
        md += [f"- {item} / {n}: {json.dumps(ex, ensure_ascii=False)}" for item, n, ex in examples[:10]]
        md.append("")
    (RESULTS / "results.md").write_text("\n".join(md), encoding="utf-8")

    with open(RESULTS / "usefulness_sheet.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["item", "system", "output", "usefulness_1_to_5", "notes"])
        for r in qa_rows + dr_rows:
            for n, m in r["systems"].items():
                w.writerow([r.get("id") or r.get("draft_type"), n, m["output"], "", ""])
    return qa_agg, dr_agg, rt_agg, fabrications


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["all", "dev", "heldout"], default="all")
    parser.add_argument("--skip-drafts", action="store_true")
    parser.add_argument("--pause", type=float, default=0.0, help="seconds to wait between steps")
    args = parser.parse_args()

    use_eval_store()
    spec = json.loads((EVAL_DIR / "queries.json").read_text(encoding="utf-8"))
    cases = [c for c in spec["cases"] if args.split == "all" or c["split"] == args.split]
    all_results = []
    for case in cases:
        print(f"Case {case['case_id']} ({case['split']})")
        documents = load_case(case)
        chunks = drafter.all_chunks(documents)
        result = {"case_id": case["case_id"], "split": case["split"],
                  "contradictions": eval_contradictions(case, documents),
                  "retrieval": eval_retrieval(case, chunks, args.pause),
                  "questions": eval_questions(case, documents, chunks, args.pause),
                  "drafts": [] if args.skip_drafts else eval_drafts(case, documents, chunks, args.pause)}
        all_results.append(result)

    qa_agg, dr_agg, rt_agg, fabrications = write_report(all_results, args.split)
    (RESULTS / "results.json").write_text(json.dumps(
        {"split": args.split, "questions": qa_agg, "drafts": dr_agg, "retrieval": rt_agg,
         "cases": all_results}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n" + (RESULTS / "results.md").read_text(encoding="utf-8"))
    print(f"Saved: {RESULTS / 'results.md'}, results.json, usefulness_sheet.csv")
    sys.exit(1 if fabrications else 0)


if __name__ == "__main__":
    main()
