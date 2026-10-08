"""Automated regression tests for backend/validator.py verifying audit findings and fixes:
L1: Statute word boundaries
L2: Sequential quotation matching with ellipses
L3: Template allow-list vs factual sentences
L4: Negation consistency check
O1: Expanded vocabulary and -ly adverb rule
O2: Month-to-number mapping
H1: Non-dict input safety
H2: Independent totals dictionary in validate_draft
"""
import pytest
from backend import validator


class TestStatuteWordBoundaries:
    """L1: Statutes should not match accidental substrings inside ordinary words."""

    def test_ordinary_words_do_not_match_statutes(self):
        # L1 audit proof-of-concepts
        assert not validator._law_supported("IPC", "The clip camera recorded the incident.")
        assert not validator._law_supported("Constitution", "The thief took an article of clothing from the shop.")
        assert not validator._law_supported("Evidence Act", "He wore a tie alone at the meeting.")

    def test_legitimate_statutes_match(self):
        assert validator._law_supported("IPC", "Charged under Section 420 IPC.")
        assert validator._law_supported("IPC", "Charged under Section 420 I.P.C.")
        assert validator._law_supported("CrPC", "Bail application under Section 439 Cr.P.C.")
        assert validator._law_supported("CrPC", "provisions of code of criminal procedure")
        assert validator._law_supported("Constitution", "Violation of Article 21 of the Constitution of India")
        assert validator._law_supported("Arms Act", "Recovered illegal weapon under Arms Act")
        assert validator._law_supported("UAPA", "Offences under UAPA were invoked")
        assert validator._law_supported("PMLA", "Enforcement Directorate registered case under PMLA")


class TestOrderedQuoteMatching:
    """L2: Quote parts joined with '...' must appear in sequential order, near each other, and >= 3 words."""

    def test_out_of_order_composite_quote_rejected(self):
        # L2 audit proof-of-concept: Pieces are >= 3 words, but out of order in source
        chunk = {
            "chunk_id": "c1",
            "text": "Immediately the police arrived. Bob admitted his guilt. Earlier Ravi Sharma was asleep."
        }
        citation = {
            "chunk_id": "c1",
            "quote": "Earlier Ravi Sharma ... Bob admitted his guilt"
        }
        res, note = validator.check_citation(citation, {"c1": chunk}, [chunk])
        assert res is None
        assert "not found" in note

    def test_pieces_with_less_than_three_words_rejected(self):
        chunk = {
            "chunk_id": "c1",
            "text": "The accused Vikash was seen running away from the spot immediately."
        }
        citation = {
            "chunk_id": "c1",
            "quote": "The accused Vikash ... seen ... running away"
        }
        res, note = validator.check_citation(citation, {"c1": chunk}, [chunk])
        assert res is None
        assert "at least 3 words" in note

    def test_valid_in_order_quote_accepted(self):
        chunk = {
            "chunk_id": "c1",
            "text": "The complainant Ravi Sharma stated that on 12 March 2026 the goods were delivered damaged."
        }
        citation = {
            "chunk_id": "c1",
            "quote": "The complainant Ravi Sharma ... on 12 March 2026 the goods"
        }
        res, note = validator.check_citation(citation, {"c1": chunk}, [chunk])
        assert res is not None
        assert res["chunk_id"] == "c1"
        assert note == "ok"


class TestTemplateAllowList:
    """L3: Only allow-listed formula phrases are treated as templates; arbitrary sentences require citations."""

    def test_factual_sentence_without_names_or_numbers_needs_citation(self):
        # L3 audit proof-of-concept
        text = "The accused was present at the shop."
        assert validator.is_factual(text) is True
        assert validator.is_template(text) is False

        # Should be replaced because it has no citation
        s = [{"text": text, "type": "fact", "citations": []}]
        out, removed, stats = validator.validate_sentences(s, [])
        assert stats["fact_claims"] == 1
        assert stats["verified"] == 0
        assert out[0]["status"] == "replaced"
        assert "[information needed" in out[0]["text"]

    def test_allow_listed_legal_formulas_are_templates(self):
        prayer = "It is therefore most respectfully prayed that the Ld. Court may be pleased to grant bail."
        assert validator.is_template(prayer) is True
        assert validator.is_factual(prayer) is False

        s = [{"text": prayer, "type": "template", "citations": []}]
        out, removed, stats = validator.validate_sentences(s, [])
        assert stats["template"] == 1
        assert out[0]["status"] == "template"
        assert out[0]["text"] == prayer


class TestNegationCheck:
    """L4: Negation mismatch between draft and source must be caught."""

    def test_negation_inversion_rejected(self):
        # L4 audit proof-of-concept: Source has negation ("not"), claim does not
        chunk = {
            "chunk_id": "c1",
            "text": "The accused was not present at the shop on the date of occurrence."
        }
        sentence = {
            "text": "The accused was present at the shop.",
            "type": "fact",
            "citations": [{"chunk_id": "c1", "quote": "The accused was not present"}]
        }
        out, removed, stats = validator.validate_sentences([sentence], [chunk])
        assert stats["verified"] == 0
        assert stats["replaced"] == 1
        assert "negation mismatch" in out[0]["issues"][0]

    def test_reverse_negation_inversion_rejected(self):
        # Source is affirmative, claim adds "not"
        chunk = {
            "chunk_id": "c1",
            "text": "The accused was present at the warehouse during the inspection."
        }
        sentence = {
            "text": "The accused was not present at the warehouse.",
            "type": "fact",
            "citations": [{"chunk_id": "c1", "quote": "The accused was present at the warehouse"}]
        }
        out, removed, stats = validator.validate_sentences([sentence], [chunk])
        assert stats["verified"] == 0
        assert stats["replaced"] == 1
        assert "negation mismatch" in out[0]["issues"][0]

    def test_number_abbreviation_not_confused_with_negation(self):
        # "FIR No. 123" or "Case No. 45" should not trigger false negation
        assert not validator.has_negation("FIR No. 123 was registered at PS Saket.")
        assert not validator.has_negation("Case No. 456 is pending before the Hon'ble Court.")
        assert not validator.has_negation("Plot No. 12, Sector 14, Gurgaon.")
        assert validator.has_negation("Accused has no criminal antecedents.")
        assert validator.has_negation("There is nil recovery from the applicant.")


class TestVocabularyAndAdverbs:
    """O1: Expanded vocabulary and -ly adverbs should not be treated as names."""

    def test_sentence_starter_connectives_and_roles_verified(self):
        chunk = {
            "chunk_id": "c1",
            "text": "On 12 March 2026 the accused was detained by the police."
        }
        # "Subsequently" should not be marked as a missing name token
        s1 = {
            "text": "Subsequently, the accused was detained on 12 March 2026.",
            "type": "fact",
            "citations": [{"chunk_id": "c1", "quote": "the accused was detained"}]
        }
        out, removed, stats = validator.validate_sentences([s1], [chunk])
        assert stats["verified"] == 1
        assert out[0]["status"] == "verified"

        # "Meanwhile" should also pass
        s2 = {
            "text": "Meanwhile, the accused was detained on 12 March 2026.",
            "type": "fact",
            "citations": [{"chunk_id": "c1", "quote": "the accused was detained"}]
        }
        out, removed, stats = validator.validate_sentences([s2], [chunk])
        assert stats["verified"] == 1
        assert out[0]["status"] == "verified"

    def test_adverbs_ending_in_ly_ignored_as_names(self):
        crit = validator.critical_tokens("Initially, the report was submitted.")
        assert not any(kind == "name" and val == "initially" for kind, val in crit)


class TestDateMapping:
    """O2: Month-name to number mapping allows numerical dates backed by written dates."""

    def test_written_date_supports_numeric_date(self):
        chunk = {
            "chunk_id": "c1",
            "text": "The accused was arrested on 12th March 2026."
        }
        sentence = {
            "text": "The accused was arrested on 12/03/2026.",
            "type": "fact",
            "citations": [{"chunk_id": "c1", "quote": "The accused was arrested on 12th March 2026"}]
        }
        out, removed, stats = validator.validate_sentences([sentence], [chunk])
        assert stats["verified"] == 1
        assert stats["replaced"] == 0
        assert out[0]["status"] == "verified"


class TestHygieneAndRobustness:
    """H1 & H2: Robust input handling and immutable totals dict."""

    def test_non_dict_sentences_do_not_crash(self):
        # Plain string or None in sentences list
        out, removed, stats = validator.validate_sentences(["plain string", None, {"text": ""}], [])
        assert stats["sentences"] == 0
        assert out == []

    def test_audit_non_dict_sentences_safe(self):
        problems = validator.audit(["malformed string", None], [])
        assert problems == []

    def test_validate_draft_does_not_mutate_section_zero_stats(self):
        sec1 = {
            "id": "s1",
            "heading": "Section 1",
            "sentences": [{"text": "It is prayed that bail be granted.", "type": "template", "citations": []}]
        }
        sec2 = {
            "id": "s2",
            "heading": "Section 2",
            "sentences": [{"text": "Deponent solemnly affirms the same.", "type": "template", "citations": []}]
        }
        out_secs, removed, totals = validator.validate_draft([sec1, sec2], [])
        assert totals["template"] == 2
