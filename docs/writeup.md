# Agentic Legal Assistant: verifiable case review and drafting

**Team Data Drifters, HACKNEX 2026, problem HNX26EPS01**

## 1. Problem and scope

Legal assistants fail when they sound right but are not traceable. We built for one bar: **every fact and citation shown to the user must be traceable to an exact quote in the uploaded documents**. We went deep on **Case Review + Legal Drafting** (bail application first, then legal notice and affidavit) and added **grounded Q&A** (RAG chat), a **missing-info + confidence report**, and **contradiction detection**.

## 2. Key idea: the model proposes, code verifies

| Step | Who does it | Why |
|---|---|---|
| Read PDF text (PyMuPDF; Gemini OCR only for scanned pages) | Code | The source text cannot be invented |
| Split into passages, assign IDs like `doc1-p3-para2` | Code | IDs cannot be invented |
| Extract facts, each with chunk ID + exact quote | Gemini, then code keeps a fact only if its quote is in that chunk | Facts start verified |
| Missing-info checklist and confidence | Code | Deterministic and explainable |
| Contradictions | Code rule (same field, different values) + Gemini suggestions; both quotes must exist | Suggestions are verified before they are shown |
| Retrieval | BM25 + Gemini embeddings, fused with RRF, then a Gemini reranker | Keywords and meaning; ranks real passages only |
| Draft / answer as JSON sentences: `text`, `type` (fact / template / missing), `citations` (chunk ID + quote) | Gemini | Every claim carries its evidence |
| **Validator** | **Python** | Checks each citation and each claim; anything unsupported is removed or replaced by `[information needed]` |

### The validator (`backend/validator.py`)
1. **Citation check.** The chunk ID must exist and the quote must be inside that chunk, after normalising spaces, quotes and dashes. A correct quote with a wrong ID is re-linked to the right chunk. A quote that exists nowhere is removed.
2. **Claim check.** Every *critical token* in the sentence must appear in the cited passage. Critical tokens are names, numbers, dates, section numbers, Acts/statutes (IPC, CrPC, BNS, BNSS...) and case-law markers. A real quote attached to a sentence that adds an invented age or date therefore still fails.
3. **Template check.** Standard legal wording (for example the prayer) may contain **no** critical tokens and no factual statements. Otherwise it is treated as a fact and needs a citation.
4. **Abstain over guess.** A failed fact becomes `[information needed: ...]`; a failed template line is removed. Every change is listed in the UI.
5. **Independent audit.** `audit()` re-checks the final output; the UI shows "fabrications left", which must be 0.

The model is never asked to grade itself. All verification is deterministic Python.

### Backup mode
If Gemini is down (503 or quota errors), the system degrades but stays grounded. Retrieval falls back to BM25, and contradiction detection keeps its rule-based check. Drafting builds a fact-only template from verified facts, and Q&A quotes the top passages word for word. All of it still passes through the validator.

## 3. Evaluation

**Setup** (`eval/run_eval.py`, `eval/queries.json`). Each case has documents and questions with known gold passages and expected answer strings, plus unanswerable questions, where the right behaviour is to abstain. Splits: `dev` is the surrender-cum-bail petition we developed with; `heldout` is a 3-document theft case (FIR, arrest memo, remand report) with a deliberate arrest-date conflict, never used for tuning. Judges' unseen documents can be added the same way.

**Systems.** All use the same Gemini model:
- `baseline`: plain Gemini on the full document text, told to use only the documents; no chunk IDs, no validator.
- `ours_no_validator`: retrieval + grounded JSON prompt, raw output (validator ablation).
- `ours_full`: retrieval + grounded prompt + validator.
- `ours_no_retrieval`: all passages + grounded prompt + validator (retrieval ablation).

**Metrics.** The same scorer is used for every system:
- *Groundedness %*: factual sentences whose names, numbers, dates and sections all appear in one or two passages that also share at least 50% of the sentence's content words.
- *Fabrications*: factual sentences containing a name, number, date or law that appears nowhere in the case, plus citations whose quote is not in any passage.
- *Answer accuracy*: expected strings are present in the answer.
- *Correct abstention*: on unanswerable questions, the system says information is missing and invents nothing.
- *Retrieval*: recall@5, hit@5 and MRR@10 of the gold passages for `bm25` (baseline), `dense`, `hybrid` and `hybrid_rerank`.

### Results

> Fill these tables from `eval/results/results.md` after running `python eval/run_eval.py --split heldout` (and once with `--split dev`). Do not edit the numbers by hand.

**Questions (held-out)**

| System | Groundedness % | Fabricated claims | Fabricated citations | Answer accuracy % | Correct abstention % |
|---|---|---|---|---|---|
| baseline | | | | | |
| ours_no_validator | | | | | |
| **ours_full** | | **0** | **0** | | |
| ours_no_retrieval | | | | | |

**Drafts (bail application)**

| System | Groundedness % | Fabricated claims | Fabricated citations | Fact coverage % |
|---|---|---|---|---|
| baseline | | | | |
| ours_no_validator | | | | |
| **ours_full** | | **0** | **0** | |

**Retrieval**

| Mode | Recall@5 | Hit@5 | MRR@10 |
|---|---|---|---|
| bm25 (baseline) | | | |
| dense | | | |
| hybrid | | | |
| hybrid_rerank | | | |

**Contradiction detection:** the arrest-date conflict (12.03.2024 vs 13.03.2024) is detected: yes / no.

### What the ablation shows (write 3–4 sentences after the run)
- Validator on vs off: change in fabrications and groundedness.
- Retrieval on vs off: change in answer accuracy and groundedness.
- Which retrieval mode worked best, and on which kind of question (wording mismatch, for example "live" vs "residing").

## 4. Limitations (honest)
- **Meaning is not fully checked.** The validator checks citations and critical tokens. A sentence that uses only real words but reverses their meaning (for example a missing "not") can pass. The citation lets a human check it in one click.
- **Strict name detection.** A capitalised word that is not in our common-word list must appear in the sources. This can occasionally turn a correct sentence into `[information needed]`. We accept that cost: abstaining is safer than guessing.
- **No outside legal research.** The system never cites a section, Act or judgment that is not in the uploaded documents, so it cannot add supporting case law. This is deliberate under the zero-fabrication rule; a verified law database would be the next step.
- **Small evaluation set.** Our held-out case is small and created by us. The real test is the judges' unseen documents, which the same scripts can evaluate.
- Field patterns for the missing-info checklist are tuned for Indian criminal petitions; new document types need new patterns.

## 5. How to reproduce
See `README.md`: install, add the Gemini key, `python app.py` for the dashboard, `python eval/run_eval.py` for the numbers.
