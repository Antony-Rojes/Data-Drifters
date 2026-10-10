# Agentic Legal Assistant (HACKNEX 2026, HNX26EPS01), Team Data Drifters

Upload case PDFs, get a missing-info and contradiction report, generate a bail application, legal notice or affidavit, and ask questions. **Every fact carries a clickable citation (chunk ID + exact quote), and a Python validator removes anything it cannot verify.**

## Features
1. **Upload and parsing:** PyMuPDF text, Gemini OCR only for scanned pages; facts kept only if their quote is in the source.
2. **Hybrid retrieval:** BM25 + Gemini embeddings (RRF fusion) + Gemini reranker; falls back to BM25 if Gemini is down.
3. **Grounded drafting:** bail application, legal notice, affidavit; every sentence typed fact / template / missing.
4. **Citation and claim validator:** pure Python; checks quotes and every name/number/date/section/Act.
5. **Missing-info and confidence report** shown before drafting.
6. **Contradiction detection** across and within documents (rule + verified Gemini suggestions).
7. **Grounded Q&A (RAG chat):** multi-turn, same validator.

## Setup (Windows PowerShell)
```powershell
cd "D:\projects\Data Drifters"
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env      # then open .env and paste your Gemini API key
python app.py
```


## Using the dashboard
1. **Upload** one or more PDFs of the same case.
2. **Analyze case:** check found / blank / missing items and contradictions.
3. **Generate draft:** click any `[n]` to see the exact source passage highlighted. Download or print.
4. **Ask** questions; answers carry citations too.
5. **New Case** archives everything to `data/archive` and starts empty (use it before each judge's documents).

## Evaluation
```powershell
python eval/make_sample_case.py              # (already included) creates the held-out sample PDFs
python eval/run_eval.py --split heldout      # baseline vs ours + ablations
python eval/run_eval.py --split dev
python eval/run_eval.py --skip-drafts --pause 4   # fewer calls / slower, for free-tier limits
```
Results go to `eval/results/results.md` (tables), `results.json` (details) and `usefulness_sheet.csv` (rate 1–5 by hand). The script exits with an error code if `ours_full` has any fabrication. To add unseen documents, put the PDFs in `eval/heldout/<case_name>/` and add a case to `eval/queries.json`.

## Project structure
```
app.py                 Flask routes: / /upload /case /chunk/<id> /pdf/<doc> /reset /draft-types
                       /analyze /retrieve /draft /draft/<type>.txt /validate /ask
backend/
  config.py            paths, limits, model names (.env)
  storage.py           single store.json, thread-safe atomic writes, archive on New Case
  gemini_client.py     Gemini calls with retry/backoff + fallback model, embeddings
  extractor.py         PDF -> chunks with code-assigned IDs -> verified facts
  analyzer.py          missing-info + confidence report, contradiction detection
  retrieval.py         BM25 + embeddings + RRF + reranker (4 modes for ablation)
  validator.py         citation + claim validator, final audit
  drafter.py           grounded drafting + backup template mode
  qa.py                grounded Q&A
  prompts.py           all prompts
frontend/              index.html, css/style.css, js/{source,upload,report,draft,ask}.js
eval/                  queries.json, baseline.py, run_eval.py, make_sample_case.py, heldout/, results/
docs/                  writeup.md, demo_checklist.md
data/ (git-ignored)    uploads/, cache/store.json, archive/
```

## Design rules
- Source text and chunk IDs come from code, never from the model.
- Gemini returns JSON with chunk IDs and exact quotes; Python verifies them.
- Facts are stored per document, so contradictions can be found.
- Abstain over guess: unsupported content becomes `[information needed]`.
- Never cite a law or judgment that is not in the uploaded documents.
