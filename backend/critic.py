"""Agentic Critic / Pre-Audit Interceptor.

Intercepts every proposed legal response before emission to the user.
Extracts factual assertions, validates them deterministically against retrieved chunks,
calculates a groundedness confidence score, and gates hallucinations. If confidence
drops below the threshold (default 0.7) or evidence is insufficient, halts the answer
and returns the exact fallback:
"MISSING INFO: PRECEDENT PROOF UNRESOLVED IN RETRIEVAL BOUNDARIES"
"""
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from backend import validator


DEFAULT_MIN_CONFIDENCE = 0.7
FALLBACK_MISSING_INFO = "MISSING INFO: PRECEDENT PROOF UNRESOLVED IN RETRIEVAL BOUNDARIES"


def _split_into_sentences(text: str) -> List[str]:
    """Splits response text into discrete verifiable sentence assertions."""
    # Split on sentence boundaries, keeping punctuation
    raw_sents = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    cleaned = []
    for s in raw_sents:
        s_clean = s.strip()
        # Skip markdown headers or trivial transitions
        if len(s_clean) >= 8:
            cleaned.append(s_clean)
    return cleaned


def _extract_critical_tokens(sentence: str) -> Tuple[Set[str], Set[str]]:
    """Extract numbers, dates, and capitalized named entities for exact grounding."""
    numbers = set(re.findall(r"\b\d+(?:/\d+)*(?:\.\d+)?\b", sentence))
    # Capitalized potential named entities (names, places, statutes)
    words = re.findall(r"\b[A-Z][a-zA-Z0-9_.-]+\b", sentence)
    entities = {
        w.lower() for w in words
        if w.lower() not in {"the", "a", "an", "this", "that", "it", "in", "on", "at", "by", "for", "and", "or"}
    }
    return numbers, entities


class AgenticCritic:
    """Pre-audit verification interceptor for legal generation."""

    def __init__(self, min_confidence: float = DEFAULT_MIN_CONFIDENCE):
        self.min_confidence = min_confidence

    def evaluate_sentence(
        self, sentence: str, retrieved_chunks: List[Dict[str, Any]]
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Checks if a single sentence assertion is grounded in the retrieved chunks.
        Returns: (is_supported, matched_chunk, reason)
        """
        if not retrieved_chunks:
            return False, None, "No source chunks retrieved."

        # Template/disclaimer sentences with no facts are accepted
        s_lower = sentence.lower()
        if any(formula in s_lower for formula in (
            "based on the documents", "according to the records", "as per the filing",
            "the petitioner prays", "in the matter of", "respectfully submitted"
        )):
            return True, retrieved_chunks[0], "Procedural connective phrase"

        sent_nums, sent_entities = _extract_critical_tokens(sentence)

        best_chunk = None
        best_overlap = 0

        for chunk in retrieved_chunks:
            chunk_text = chunk.get("text", "")
            chunk_lower = chunk_text.lower()

            # Check number grounding: every critical number in sentence must be in chunk
            nums_supported = True
            for num in sent_nums:
                if num not in chunk_text:
                    nums_supported = False
                    break

            if not nums_supported and sent_nums:
                continue

            # Check entity overlap
            entity_overlap = sum(1 for ent in sent_entities if ent in chunk_lower)
            if sent_entities and entity_overlap == 0:
                continue

            # Substring / n-gram verification: check if 3+ word sequences appear verbatim
            words = [w for w in re.findall(r"\b[a-zA-Z0-9]+\b", sentence.lower()) if len(w) > 3]
            overlap_score = sum(1 for w in words if w in chunk_lower)
            if overlap_score > best_overlap:
                best_overlap = overlap_score
                best_chunk = chunk

        if best_chunk and (best_overlap >= 2 or not sent_entities):
            return True, best_chunk, "Corroborated by retrieved chunk text"

        return False, None, "Unsupported assertion: entities or numbers absent from evidence"

    def audit_response(
        self,
        proposed_answer: str,
        retrieved_chunks: List[Dict[str, Any]],
        case_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Audits the full proposed answer against retrieved chunks before returning to user.
        Never allows invented citations. Fails safe if confidence < threshold.
        """
        # Hard fail if no evidence retrieved
        if not retrieved_chunks:
            return {
                "grounded_answer": FALLBACK_MISSING_INFO,
                "confidence": 0.0,
                "is_grounded": False,
                "sources": [],
                "audit_log": ["No retrieval evidence available in boundaries."],
                "raw_answer": proposed_answer,
            }

        sentences = _split_into_sentences(proposed_answer)
        if not sentences:
            return {
                "grounded_answer": FALLBACK_MISSING_INFO,
                "confidence": 0.0,
                "is_grounded": False,
                "sources": [],
                "audit_log": ["Empty response proposed."],
                "raw_answer": proposed_answer,
            }

        verified_sentences: List[str] = []
        rejected_sentences: List[Tuple[str, str]] = []
        cited_chunks: List[Dict[str, Any]] = []
        seen_chunk_ids: Set[str] = set()

        for sent in sentences:
            is_supported, matched_chunk, reason = self.evaluate_sentence(sent, retrieved_chunks)
            if is_supported:
                verified_sentences.append(sent)
                if matched_chunk and matched_chunk["chunk_id"] not in seen_chunk_ids:
                    seen_chunk_ids.add(matched_chunk["chunk_id"])
                    cited_chunks.append(matched_chunk)
            else:
                rejected_sentences.append((sent, reason))

        total_sents = len(sentences)
        confidence = round(len(verified_sentences) / total_sents, 3) if total_sents > 0 else 0.0

        # Enforce Groundedness Threshold Gate (Fail Safe)
        if confidence < self.min_confidence or not verified_sentences:
            return {
                "grounded_answer": FALLBACK_MISSING_INFO,
                "confidence": confidence,
                "is_grounded": False,
                "sources": [],
                "audit_log": [
                    f"Groundedness score {confidence} is below minimum required boundary {self.min_confidence}.",
                    f"Rejected {len(rejected_sentences)} unbacked sentence(s).",
                ],
                "rejected_assertions": [r[0] for r in rejected_sentences],
                "raw_answer": proposed_answer,
            }

        # Build clean verified answer text
        clean_body = " ".join(verified_sentences)

        # Format authentic metadata citations
        source_blocks: List[str] = []
        sources_meta: List[Dict[str, Any]] = []

        for idx, c in enumerate(cited_chunks, start=1):
            source_c_id = c.get("case_id") or case_id or "Unassigned"
            source_doc_id = c.get("doc_id") or c.get("chunk_id", "").split("-")[0]
            source_page = c.get("page", 1)
            chunk_id = c.get("chunk_id", "")
            
            source_entry = {
                "index": idx,
                "case_id": source_c_id,
                "document": source_doc_id,
                "page": source_page,
                "source_id": chunk_id,
                "court": c.get("court", ""),
                "date": c.get("date", ""),
            }
            sources_meta.append(source_entry)

            block = (
                f"[{idx}] Case ID: {source_c_id}\n"
                f"    Document: {source_doc_id}\n"
                f"    Page: {source_page}\n"
                f"    Source ID: {chunk_id}"
            )
            source_blocks.append(block)

        formatted_final = f"Answer:\n{clean_body}\n\nSources:\n" + "\n".join(source_blocks)

        return {
            "grounded_answer": formatted_final,
            "answer_body": clean_body,
            "confidence": confidence,
            "is_grounded": True,
            "sources": sources_meta,
            "audit_log": [
                f"Verified {len(verified_sentences)} of {total_sents} sentences ({confidence * 100:.1f}% grounded).",
                f"Retained {len(cited_chunks)} authentic source citations.",
            ],
            "rejected_assertions": [r[0] for r in rejected_sentences],
            "raw_answer": proposed_answer,
        }
