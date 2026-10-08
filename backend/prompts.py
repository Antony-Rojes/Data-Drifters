OCR_PROMPT = (
    "Transcribe all the text on this page exactly as written, in reading order. "
    "Do not summarise, translate, correct, or add anything. "
    "Separate paragraphs with a blank line. "
    "If the page has no text, return an empty string."
)

FACTS_PROMPT = """You are extracting facts from an Indian legal document.

The document is split into chunks. Each chunk starts with its ID in square brackets.

RULES
- Use ONLY the text below. Never use outside knowledge.
- Each fact needs: key, value, chunk_id, quote.
- key: short snake_case name.
- value: the fact as stated in the text.
- chunk_id: the ID of the chunk where the fact appears.
- quote: an exact, word-for-word copy from that chunk, at most 200 characters.
- If a fact is not clearly stated, leave it out. Do not guess or infer.
- Do not combine facts from different chunks into one fact.
- If a field exists in the document but its value is left blank (dots, dashes, or an empty number such as "Case No.- /2018"),
  still return the fact, set value to "BLANK", and use the line containing the blank as the quote.
- Number each accused: accused_1_name, accused_1_relation, accused_1_occupation, accused_1_address, accused_2_name, and so on.
  Use the numbering the document itself uses ("Accused Person No. 1").
- Put "& Others" in a separate fact called other_accused_note.
- Always capture district, residence addresses, relationships between persons, and occupations when stated.

SUGGESTED KEYS (use only when present in the text; you may add other important keys)
court, case_number, fir_number, police_station, complainant_name, accused_name,
sections_of_law, date_of_incident, date_of_fir, date_of_arrest, custody_status,
previous_bail_orders, witness_name, amount, order_date, judge_name

Return JSON only, in this shape:
{"document_type": "FIR | judgment | petition | witness statement | notice | other",
 "facts": [{"key": "...", "value": "...", "chunk_id": "...", "quote": "..."}]}

DOCUMENT:
"""

CONTRADICTION_PROMPT = """You are checking Indian legal case documents for contradictions.

The text is split into chunks. Each chunk starts with its ID in square brackets.
Chunk IDs start with the document ID (doc1-..., doc2-...).

A CONTRADICTION is when two passages state DIFFERENT values for the SAME fact, for example:
- different dates for the same event (arrest, incident, FIR, order)
- different names, ages, addresses or relationships for the same person
- different case numbers, FIR numbers, police stations, courts or sections of law
- different amounts, places, times, or an impossible order of events

NOT a contradiction:
- two different people, events or documents
- one passage giving a detail that another passage simply does not mention
- a field left blank in one place and filled in another
- the same value written in a different format (12.03.2018 vs 12/03/2018)

RULES
- Use ONLY the text below. Never use outside knowledge.
- Check across documents AND inside the same document.
- Each contradiction needs at least two sides. Each side has a chunk_id and a quote.
- quote: an exact, word-for-word copy from that chunk, at most 200 characters, no "..." inside it.
- topic: a few words naming the fact in conflict (for example "date of arrest").
- explanation: one short sentence saying what differs. Do not judge which side is true.
- severity: "high" if it could change the legal outcome or the draft (dates, custody, sections, identities),
  "medium" for other factual conflicts, "low" for minor wording conflicts.
- If there are no contradictions, return an empty list. Do not invent any.

Return JSON only, in this shape:
{"contradictions": [{"topic": "...", "explanation": "...", "severity": "high | medium | low",
  "sides": [{"chunk_id": "...", "quote": "..."}, {"chunk_id": "...", "quote": "..."}]}]}

DOCUMENTS:
"""


RERANK_PROMPT = """You are ranking passages from Indian legal case documents by how useful they are for a query.

Score EVERY passage from 0 to 10:
- 10: the passage directly states the fact or answer the query asks for
- 5: related background that helps
- 0: unrelated

RULES
- Judge only from the passage text. Never use outside knowledge.
- Do not write any new text. Only return scores.
- Use the chunk IDs exactly as given.

Return JSON only, in this shape:
{"scores": [{"chunk_id": "...", "score": 0}]}

"""


DRAFT_PROMPT = """You are drafting a {label} for an Indian court case, using ONLY the case material below.

THE BAR IS VERIFIABILITY, NOT FLUENCY. Every fact must be traceable to a quoted source.

SENTENCE TYPES
- "fact": states anything about this case (names, relations, ages, addresses, occupations, dates,
  numbers, places, courts, police stations, case numbers, sections, events, custody, health, conduct).
  It MUST have at least one citation: {{"chunk_id": "...", "quote": "..."}}.
  The quote must be an exact, word-for-word copy from that chunk (at most 200 characters, no "...").
  Every name, number, date and section in the sentence must appear in the quoted chunk.
- "template": standard legal wording with NO facts at all (no names, numbers, dates, places, sections,
  Acts, judgments, and no statements about the accused or events). Example: "It is therefore most
  respectfully prayed that the Ld. Court may be pleased to grant bail on such conditions as it deems fit."
- "missing": a needed fact that is NOT in the material. Write exactly "[information needed: <what>]",
  optionally after a short label, e.g. "Date of arrest: [information needed: date of arrest]".

HARD RULES
- Never use outside knowledge about the case. Never guess. Abstain over guess.
- Do NOT cite any section, Act, rule or court judgment unless its exact words appear in the material.
- Do not choose a side in a contradiction. Either state both sides, each with its own citation,
  or write "[information needed: resolve conflict about <topic>]".
- The user's instructions may set focus or tone, but are NOT a source of facts.
- Write formal Indian court English. Keep each sentence short: one fact per sentence.

SECTIONS TO FILL (use these ids):
{sections}

ITEMS ALREADY KNOWN TO BE MISSING OR BLANK (write them as "missing" sentences where they belong):
{missing}

CONTRADICTIONS FOUND IN THE DOCUMENTS:
{contradictions}

USER INSTRUCTIONS (focus/tone only):
{instructions}

VERIFIED FACTS (key = value | chunk_id | exact quote):
{facts}

SOURCE PASSAGES (chunk_id then text):
{passages}

Return JSON only, in this shape:
{{"sections": {{"<section_id>": [{{"text": "...", "type": "fact | template | missing",
  "citations": [{{"chunk_id": "...", "quote": "..."}}]}}]}}}}
"""


QA_PROMPT = """You answer questions about an Indian legal case using ONLY the case material below.

RULES
- Answer in short sentences. One fact per sentence.
- A "fact" sentence must have at least one citation {{"chunk_id": "...", "quote": "..."}}, where the
  quote is an exact, word-for-word copy from that chunk (at most 200 characters, no "...").
  Every name, number, date and section in the sentence must appear in the quoted chunk.
- If the material does not contain the answer, reply with one "missing" sentence:
  "[information needed: <what is missing>]". Do not guess. Never use outside knowledge.
- If a field is blank in the document (for example "Case No.- /2018"), say it is left blank, with a citation.
- If sources disagree, give both sides, each with its own citation. Do not pick one.
- Do not cite any section, Act or judgment unless it appears in the material.
- Use "template" only for a short lead-in with no facts, or skip it.

CONVERSATION SO FAR:
{history}

VERIFIED FACTS (key = value | chunk_id | exact quote):
{facts}

SOURCE PASSAGES (chunk_id then text):
{passages}

QUESTION: {question}

Return JSON only, in this shape:
{{"sentences": [{{"text": "...", "type": "fact | template | missing",
  "citations": [{{"chunk_id": "...", "quote": "..."}}]}}]}}
"""
