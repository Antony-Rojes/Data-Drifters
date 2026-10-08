# Demo and judging checklist

## The day before
- [ ] `python -m pip install -r requirements.txt` in the venv; `python app.py` starts without errors.
- [ ] `.env` has the key, `GEMINI_FALLBACK_MODEL` set (backup when the main model is busy).
- [ ] Run `python eval/run_eval.py --split heldout` and `--split dev`; copy the tables into `docs/writeup.md`.
- [ ] Zero-fabrication gate in `eval/results/results.md` says **PASS**. If not, open `results.json`, search `fabricated_examples`, and read each one.
- [ ] Read 5 drafts/answers yourself and fill a few rows of `usefulness_sheet.csv`.
- [ ] **Backup snapshot:** upload the demo PDFs, run Analyze + Draft (all three types) + 2–3 questions, then copy
      `data\cache\store.json` to `data\demo_backup.json`.

## Demo script (about 5 minutes)
1. **Problem (20 s):** "Legal AI must be verifiable, not fluent. One invented fact is a fail."
2. **New Case**, then upload the 3 sample theft-case PDFs. Open a document: show facts, click a chunk ID, and show the source highlighted.
3. **Analyze case:** readiness %, a *blank* field, a *missing* field with "check these passages", and the **arrest-date contradiction** with both quotes.
4. **Generate draft** (bail application): click two `[n]` citations. Point at the `[information needed]` gaps and the validator summary ("grounded after validator 100%, fabrications left 0"). Open "Removed or replaced by the validator" and show what it caught.
5. **Ask:** "When was the accused arrested?" The answer gives **both** dates with citations. Then ask "Has an earlier bail application been rejected?"; it should say information is needed.
6. **Results slide:** the held-out table, baseline vs ours, ablation with and without the validator, and the retrieval modes.
7. **Limitations (20 s):** meaning is not fully checked, there is no outside case law by design, and the test set is small.

## Testing the judges' unseen documents
1. Click **New Case** first, so old documents do not mix in.
2. Upload their PDFs, then **Analyze**, **Draft**, and answer their queries in **Ask**.
3. For each answer, click the citations: the highlighted quote must support the sentence.
4. If they give expected sources, compare the chunk IDs in our citations with their pages and paragraphs.

## Fabrication check (manual, 2 minutes)
- For each draft: the validator box shows **fabrications left: 0**.
- Spot-check 5 citations: open each one and confirm the quote is highlighted in the passage.
- Any name, date or section that is not cited must be inside `[information needed: ...]`.

## If Gemini returns 503 / 429 during judging
1. Wait 30–60 seconds and click again (the app already retries with backoff, then tries the fallback model).
2. Analysis still works: the missing-info report and rule-based contradictions need no Gemini.
3. Drafting falls back to the **backup template draft** (verified facts only), and Q&A quotes passages directly; the UI says so.
4. For the walkthrough, restore the snapshot: stop the app, run
   `copy data\demo_backup.json data\cache\store.json`, start the app again. All saved reports and drafts reappear.
5. Embeddings are cached in `store.json`, so a prepared case needs no new embedding calls.
