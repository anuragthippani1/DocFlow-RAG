"""Phase 0: evidence contracts and the NO UNSUPPORTED ANSWER TOKENS gate."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.evidence import (
    INVARIANT,
    Claim,
    Conflict,
    ConflictSide,
    EvidenceCoverage,
    EvidenceItem,
    EvidencePack,
    EvidenceVerdict,
    IntentResult,
    UnsupportedAnswerTokensError,
    VerdictRequiredError,
    Verifier,
    assert_generation_allowed,
    assert_no_tokens_unless_allowed,
    can_explain_conflict,
    can_generate,
    can_generate_answer,
    generation_kind,
    require_verdict,
    sse_token_events_allowed,
    verify,
)
from app.evidence.types import ProductVerdict


def _coverage(**overrides: int | str) -> EvidenceCoverage:
    payload = {
        "retrieved": 0,
        "relevant": 0,
        "supporting": 0,
        "unused": 0,
        "contradicting": 0,
        "uncertain": 0,
        "note": "",
    }
    payload.update(overrides)
    return EvidenceCoverage(**payload)


def _item(**overrides) -> EvidenceItem:
    payload = {
        "id": "e1",
        "n": 1,
        "document": "sample.pdf",
        "page": 3,
        "excerpt": "Delivery takes 12 days.",
        "excerpt_full": "Delivery takes 12 days from order confirmation.",
        "chunk_start_index": 0,
        "file_mtime_ns": 1,
        "retrieval_rank": 1,
        "relevance": "relevant",
        "stance": "supports",
    }
    payload.update(overrides)
    return EvidenceItem(**payload)


def _verdict(verdict: ProductVerdict, **overrides) -> EvidenceVerdict:
    payload = {
        "verdict": verdict,
        "unsupported_kind": (
            "no_relevant_evidence" if verdict == "unsupported" else "none"
        ),
        "reason": f"verdict is {verdict}",
        "coverage": _coverage(),
        "evidence_ids": [],
        "claims": [],
        "conflicts": [],
        "missing_information": [],
        "clarification_question": None,
    }
    payload.update(overrides)
    return EvidenceVerdict(**payload)


def test_intent_result_serializes_required_fields():
    intent = IntentResult(
        needs_clarification=True,
        clarification_question="Which supplier?",
        slots=["supplier"],
    )
    dumped = intent.model_dump()
    assert dumped["needs_clarification"] is True
    assert dumped["clarification_question"] == "Which supplier?"
    assert dumped["slots"] == ["supplier"]


def test_evidence_item_omits_fabricated_rerank_score():
    item = _item()
    dumped = item.model_dump()
    assert dumped["id"] == "e1"
    assert dumped["n"] == 1
    assert dumped["document"] == "sample.pdf"
    assert dumped["page"] == 3
    assert dumped["excerpt"]
    assert dumped["excerpt_full"]
    assert dumped["chunk_start_index"] == 0
    assert dumped["file_mtime_ns"] == 1
    assert dumped["retrieval_rank"] == 1
    assert dumped["relevance"] == "relevant"
    assert dumped["stance"] == "supports"
    assert dumped["rerank_score"] is None
    assert "confidence" not in dumped
    without_none = item.model_dump(exclude_none=True)
    assert "rerank_score" not in without_none


def test_evidence_pack_and_verdict_serialize_required_fields():
    item = _item()
    pack = EvidencePack(
        query="What is the delivery time?",
        standalone_query="What is the delivery time?",
        retriever="mmr",
        items=[item],
    )
    claim = Claim(
        id="c1",
        text="Delivery takes 12 days.",
        evidence_ids=["e1"],
        support="entailed",
        citations=[1],
    )
    conflict = Conflict(
        id="k1",
        slot="delivery_time",
        kind="duration",
        sides=[
            ConflictSide(
                evidence_id="e1",
                document="a.pdf",
                page=1,
                span="12 days",
                value="12 days",
            ),
            ConflictSide(
                evidence_id="e2",
                document="b.pdf",
                page=1,
                span="19 days",
                value="19 days",
            ),
        ],
        summary="Documents disagree on delivery time.",
    )
    verdict = _verdict(
        "supported",
        coverage=_coverage(retrieved=1, relevant=1, supporting=1),
        evidence_ids=["e1"],
        claims=[claim],
        conflicts=[conflict],
        missing_information=[],
    )

    pack_dump = pack.model_dump()
    assert pack_dump["query"] == "What is the delivery time?"
    assert pack_dump["standalone_query"] == "What is the delivery time?"
    assert pack_dump["retriever"] == "mmr"
    assert len(pack_dump["items"]) == 1
    assert pack_dump["items"][0]["id"] == "e1"

    verdict_dump = verdict.model_dump()
    for key in (
        "verdict",
        "unsupported_kind",
        "reason",
        "coverage",
        "evidence_ids",
        "claims",
        "conflicts",
        "missing_information",
        "clarification_question",
    ):
        assert key in verdict_dump
    assert verdict_dump["coverage"]["retrieved"] == 1
    assert verdict_dump["claims"][0]["citations"] == [1]
    assert len(verdict_dump["conflicts"][0]["sides"]) == 2
    assert "confidence" not in verdict_dump


def test_confidence_fields_are_rejected():
    with pytest.raises(ValidationError):
        EvidenceItem.model_validate({**_item().model_dump(), "confidence": 0.9})
    with pytest.raises(ValidationError):
        EvidenceVerdict.model_validate({**_verdict("supported").model_dump(), "confidence": 0.9})


def test_unsupported_kind_must_match_verdict():
    with pytest.raises(ValidationError):
        _verdict("unsupported", unsupported_kind="none")
    with pytest.raises(ValidationError):
        _verdict("supported", unsupported_kind="insufficient_evidence")
    insufficient = _verdict("unsupported", unsupported_kind="insufficient_evidence")
    assert insufficient.unsupported_kind == "insufficient_evidence"


@pytest.mark.parametrize(
    ("verdict", "allowed", "kind", "answer", "conflict"),
    [
        ("supported", True, "answer", True, False),
        ("conflicting", True, "conflict_explanation", False, True),
        ("unsupported", False, None, False, False),
        ("ambiguous", False, None, False, False),
    ],
)
def test_generation_gate_by_verdict(verdict, allowed, kind, answer, conflict):
    model = _verdict(verdict)
    assert can_generate(verdict) is allowed
    assert can_generate(model) is allowed
    assert generation_kind(verdict) == kind
    assert can_generate_answer(verdict) is answer
    assert can_explain_conflict(verdict) is conflict
    assert sse_token_events_allowed(verdict) is allowed


def test_supported_allows_answer_generation():
    verdict = _verdict("supported")
    assert can_generate(verdict) is True
    assert can_generate_answer(verdict) is True
    assert can_explain_conflict(verdict) is False
    assert assert_generation_allowed(verdict) == "answer"
    assert_no_tokens_unless_allowed(verdict)


def test_conflicting_allows_conflict_explanation_only():
    verdict = _verdict("conflicting")
    assert can_generate(verdict) is True
    assert can_generate_answer(verdict) is False
    assert can_explain_conflict(verdict) is True
    assert assert_generation_allowed(verdict) == "conflict_explanation"
    assert_no_tokens_unless_allowed(verdict)


def test_unsupported_forbids_generation_tokens():
    verdict = _verdict("unsupported")
    assert can_generate(verdict) is False
    assert can_generate_answer(verdict) is False
    with pytest.raises(UnsupportedAnswerTokensError, match=INVARIANT):
        assert_generation_allowed(verdict)
    with pytest.raises(UnsupportedAnswerTokensError, match=INVARIANT):
        assert_no_tokens_unless_allowed(verdict)


def test_ambiguous_forbids_generation_tokens():
    verdict = _verdict(
        "ambiguous",
        clarification_question="Which supplier lead time?",
    )
    assert can_generate(verdict) is False
    with pytest.raises(UnsupportedAnswerTokensError, match=INVARIANT):
        assert_generation_allowed(verdict)
    with pytest.raises(UnsupportedAnswerTokensError, match=INVARIANT):
        assert_no_tokens_unless_allowed(verdict)


def test_no_verdict_forbids_tokens():
    with pytest.raises(VerdictRequiredError, match=INVARIANT):
        require_verdict(None)
    with pytest.raises(UnsupportedAnswerTokensError, match=INVARIANT):
        assert_generation_allowed(None)
    with pytest.raises(UnsupportedAnswerTokensError, match=INVARIANT):
        assert_no_tokens_unless_allowed(None)


def test_verify_requires_explicit_verifier_and_does_not_call_an_llm():
    pack = EvidencePack(
        query="What is the delivery time?",
        standalone_query="What is the delivery time?",
        retriever="mmr",
        items=[],
    )
    expected = _verdict("unsupported", unsupported_kind="no_relevant_evidence")

    class RecordingVerifier:
        def __init__(self) -> None:
            self.calls: list[tuple[str, EvidencePack]] = []

        def verify(self, question: str, evidence_pack: EvidencePack) -> EvidenceVerdict:
            self.calls.append((question, evidence_pack))
            return expected

    backend = RecordingVerifier()
    assert isinstance(backend, Verifier)
    result = verify("What is the delivery time?", pack, verifier=backend)
    assert result is expected
    assert backend.calls == [("What is the delivery time?", pack)]
    with pytest.raises(VerdictRequiredError):
        verify("What is the delivery time?", pack, verifier=None)
