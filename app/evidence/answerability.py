"""Answerability guards, coverage, and product abstain/clarify templates.

NO UNSUPPORTED ANSWER TOKENS: these helpers never call the answer generator.
"""

from __future__ import annotations

from app.evidence.types import (
    EvidenceCoverage,
    EvidenceItem,
    EvidencePack,
    EvidenceVerdict,
    IntentResult,
    Relevance,
    Stance,
    UnsupportedKind,
)

INSUFFICIENT_EVIDENCE_ANSWER = (
    "Insufficient evidence. I couldn't find enough information in your documents "
    "to answer this reliably."
)
VERIFICATION_FAILED_REASON = (
    "Verification failed. I cannot confirm that the evidence supports an answer."
)

_RELEVANCE = {"relevant", "not_relevant", "uncertain"}
_STANCE = {"supports", "unused", "unknown", "contradicts"}


def coerce_relevance(value: object) -> Relevance:
    text = str(value or "").strip().lower()
    if text in _RELEVANCE:
        return text  # type: ignore[return-value]
    return "uncertain"


def coerce_stance(value: object) -> Stance:
    text = str(value or "").strip().lower()
    if text in {"supports", "support"}:
        return "supports"
    if text in {"unused", "not_used"}:
        return "unused"
    if text in {"contradicts", "contradict", "conflicting"}:
        return "contradicts"
    return "unknown"


def coerce_condition(value: object) -> str | None:
    text = str(value or "").strip().lower().replace(" ", "_")
    if text in {"supported_evidence", "supported"}:
        return "supported_evidence"
    if text in {"no_relevant_evidence", "no_relevant"}:
        return "no_relevant_evidence"
    if text in {"insufficient_evidence", "insufficient", "uncertain", "unverified"}:
        return "insufficient_evidence"
    return None


def empty_pack(query: str, standalone_query: str | None = None) -> EvidencePack:
    return EvidencePack(
        query=query,
        standalone_query=standalone_query or query,
        retriever="mmr",
        items=[],
    )


def relabel_pack(
    pack: EvidencePack,
    labels: dict[str, tuple[Relevance, Stance]],
) -> EvidencePack:
    items: list[EvidenceItem] = []
    for item in pack.items:
        relevance, stance = labels.get(item.id, (item.relevance, item.stance))
        items.append(item.model_copy(update={"relevance": relevance, "stance": stance}))
    return pack.model_copy(update={"items": items})


def build_coverage(pack: EvidencePack) -> EvidenceCoverage:
    items = pack.items
    retrieved = len(items)
    relevant = sum(1 for item in items if item.relevance == "relevant")
    supporting = sum(1 for item in items if item.stance == "supports")
    unused = sum(1 for item in items if item.stance == "unused")
    contradicting = sum(1 for item in items if item.stance == "contradicts")
    uncertain = sum(1 for item in items if item.relevance == "uncertain")
    excerpt_word = "excerpt" if retrieved == 1 else "excerpts"
    contain_word = "contains" if relevant == 1 else "contain"
    if retrieved == 0:
        note = "No excerpts were retrieved."
    else:
        note = (
            f"{retrieved} {excerpt_word} were retrieved; "
            f"{relevant} {contain_word} evidence relevant to the question."
        )
    return EvidenceCoverage(
        retrieved=retrieved,
        relevant=relevant,
        supporting=supporting,
        unused=unused,
        contradicting=contradicting,
        uncertain=uncertain,
        note=note,
    )


def _verdict(
    *,
    verdict: str,
    unsupported_kind: UnsupportedKind,
    reason: str,
    pack: EvidencePack,
    missing_information: list[str] | None = None,
    clarification_question: str | None = None,
    evidence_ids: list[str] | None = None,
) -> EvidenceVerdict:
    items = pack.items
    if evidence_ids is None:
        evidence_ids = [
            item.id
            for item in items
            if item.stance == "supports" or item.relevance == "relevant"
        ]
    return EvidenceVerdict(
        verdict=verdict,  # type: ignore[arg-type]
        unsupported_kind=unsupported_kind,
        reason=reason,
        coverage=build_coverage(pack),
        evidence_ids=evidence_ids,
        claims=[],
        conflicts=[],
        missing_information=missing_information or [],
        clarification_question=clarification_question,
    )


def ambiguous_verdict(intent: IntentResult, question: str) -> EvidenceVerdict:
    clarification = intent.clarification_question or "Could you clarify what you would like to know?"
    return _verdict(
        verdict="ambiguous",
        unsupported_kind="none",
        reason="The question is not specific enough to retrieve supporting evidence.",
        pack=empty_pack(question),
        clarification_question=clarification,
        evidence_ids=[],
    )


def fail_closed_verdict(pack: EvidencePack, reason: str = VERIFICATION_FAILED_REASON) -> EvidenceVerdict:
    return _verdict(
        verdict="unsupported",
        unsupported_kind="insufficient_evidence",
        reason=reason,
        pack=pack,
        missing_information=["verification_failed"],
        evidence_ids=[],
    )


def apply_safety_rules(
    pack: EvidencePack,
    *,
    condition: str | None,
    reason: str,
    missing_information: list[str] | None = None,
) -> EvidenceVerdict:
    """Deterministic guards applied after parsing verifier output. Never upgrades to supported."""
    items = pack.items
    missing = missing_information or []
    all_not_relevant = bool(items) and all(item.relevance == "not_relevant" for item in items)
    all_uncertain = bool(items) and all(item.relevance == "uncertain" for item in items)
    any_supports = any(item.stance == "supports" for item in items)

    if not items:
        return _verdict(
            verdict="unsupported",
            unsupported_kind="no_relevant_evidence",
            reason=reason or "No excerpts were retrieved.",
            pack=pack,
            missing_information=missing,
            evidence_ids=[],
        )
    if all_not_relevant:
        return _verdict(
            verdict="unsupported",
            unsupported_kind="no_relevant_evidence",
            reason=reason or "Retrieved excerpts are not relevant to the question.",
            pack=pack,
            missing_information=missing,
            evidence_ids=[],
        )
    if condition != "supported_evidence":
        kind: UnsupportedKind = (
            "no_relevant_evidence"
            if condition == "no_relevant_evidence"
            else "insufficient_evidence"
        )
        return _verdict(
            verdict="unsupported",
            unsupported_kind=kind,
            reason=reason or "The retrieved evidence does not support a reliable answer.",
            pack=pack,
            missing_information=missing,
        )
    # Never convert uncertainty into supported.
    if all_uncertain and not any_supports:
        return _verdict(
            verdict="unsupported",
            unsupported_kind="insufficient_evidence",
            reason=reason or "Evidence is present but too uncertain to support an answer.",
            pack=pack,
            missing_information=missing,
        )
    return _verdict(
        verdict="supported",
        unsupported_kind="none",
        reason=reason or "The retrieved evidence supports answering the question.",
        pack=pack,
        missing_information=[],
    )


def product_answer(verdict: EvidenceVerdict) -> str:
    """Deterministic user-facing text for non-generating verdicts."""
    if verdict.verdict == "ambiguous":
        return verdict.clarification_question or "Could you clarify what you would like to know?"
    if verdict.verdict == "conflicting":
        from app.evidence.conflicts import conflict_explanation

        return conflict_explanation(verdict)
    parts = [INSUFFICIENT_EVIDENCE_ANSWER]
    if verdict.reason:
        parts.append(verdict.reason)
    if verdict.missing_information:
        parts.append("Missing information: " + "; ".join(verdict.missing_information))
    if verdict.evidence_ids:
        parts.append("Reviewed evidence: " + ", ".join(verdict.evidence_ids) + ".")
    return "\n\n".join(parts)
