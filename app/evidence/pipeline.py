"""Product evidence-first turn preparation. Does not generate answers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.evidence.answerability import (
    ambiguous_verdict,
    empty_pack,
    fail_closed_verdict,
    product_answer,
)
from app.evidence.conflicts import apply_conflicts
from app.evidence.intent import analyze_intent
from app.evidence.pack import pack_to_json, source_details_from_pack
from app.evidence.types import EvidencePack, EvidenceVerdict, IntentResult
from app.evidence.verifier import can_generate_answer, verify
from app.evidence.verify_openrouter import get_verifier
from app.logging_utils import get_logger
from app.rag_chat import run_conversational_retrieval, unique_source_names

logger = get_logger(__name__)


@dataclass
class PreparedTurn:
    intent: IntentResult
    standalone_query: str
    pack: EvidencePack
    details: list[dict[str, Any]]
    sources: list[str]
    verdict: EvidenceVerdict
    emit_sources: bool


def verify_evidence(
    question: str, pack: EvidencePack
) -> tuple[EvidencePack, EvidenceVerdict]:
    """Run the Verifier and fail closed on any error. Never generates an answer."""
    try:
        backend = get_verifier()
        verify_with_pack = getattr(backend, "verify_with_pack", None)
        if callable(verify_with_pack):
            labeled, verdict = verify_with_pack(question, pack)
            return labeled, verdict
        verdict = verify(question, pack, verifier=backend)
        return pack, verdict
    except Exception:
        logger.exception("verify_evidence failed; failing closed")
        return pack, fail_closed_verdict(pack)


def _unpack_retrieval(
    result: Any,
) -> tuple[str, list, list[dict[str, Any]], EvidencePack | None]:
    standalone, docs, details = result[0], result[1], result[2]
    pack = result[3] if len(result) > 3 else None
    return standalone, docs, details, pack


def prepare_evidence_turn(
    question: str,
    history: list[dict[str, str]],
    *,
    source_limit: int,
    analyze_intent_fn=analyze_intent,
    retrieve_fn=run_conversational_retrieval,
    verify_fn=verify_evidence,
) -> PreparedTurn:
    intent = analyze_intent_fn(question, history)
    if intent.needs_clarification:
        pack = empty_pack(question, question)
        verdict = ambiguous_verdict(intent, question)
        return PreparedTurn(
            intent=intent,
            standalone_query=question,
            pack=pack,
            details=[],
            sources=[],
            verdict=verdict,
            emit_sources=False,
        )

    retrieved = retrieve_fn(question, history)
    standalone, _docs, details, pack = _unpack_retrieval(retrieved)
    if pack is None:
        pack = empty_pack(question, standalone)
        details = details or []
    try:
        labeled, verdict = verify_fn(question, pack)
    except Exception:
        logger.exception("Verifier raised; failing closed")
        labeled, verdict = pack, fail_closed_verdict(pack)
    labeled, verdict = apply_conflicts(question, labeled, verdict)
    details = source_details_from_pack(labeled)
    sources = unique_source_names(details, source_limit)
    return PreparedTurn(
        intent=intent,
        standalone_query=standalone,
        pack=labeled,
        details=details,
        sources=sources,
        verdict=verdict,
        emit_sources=True,
    )


def verdict_payload(verdict: EvidenceVerdict) -> dict[str, Any]:
    return verdict.model_dump(mode="json", exclude_none=True)


def persistence_payload(turn: PreparedTurn) -> dict[str, Any]:
    return {
        "source_details": turn.details,
        "evidence": pack_to_json(turn.pack),
        "verdict": verdict_payload(turn.verdict),
    }


__all__ = [
    "PreparedTurn",
    "can_generate_answer",
    "persistence_payload",
    "prepare_evidence_turn",
    "product_answer",
    "verdict_payload",
    "verify_evidence",
]
