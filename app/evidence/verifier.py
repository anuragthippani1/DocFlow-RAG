"""Verifier protocol and generation-gating helpers.

NO UNSUPPORTED ANSWER TOKENS is a testable product invariant, not a prompt.

Phase 0 only establishes the contract. No LLM verifier is implemented here,
and this module is not wired into /query or /query/stream.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.evidence.types import (
    EvidencePack,
    EvidenceVerdict,
    GenerationKind,
    ProductVerdict,
)


INVARIANT = "NO UNSUPPORTED ANSWER TOKENS."


class VerdictRequiredError(RuntimeError):
    """Raised when generation is attempted without an evidence verdict."""


class UnsupportedAnswerTokensError(RuntimeError):
    """Raised when answer or conflict-explanation tokens would violate the invariant."""


@runtime_checkable
class Verifier(Protocol):
    """Sole authority on whether evidence is sufficient to answer.

    Implementations must not generate a user-facing answer. They only return
    an EvidenceVerdict. The answer generator must never decide sufficiency.
    """

    def verify(self, question: str, evidence_pack: EvidencePack) -> EvidenceVerdict:
        ...


def verify(
    question: str,
    evidence_pack: EvidencePack,
    *,
    verifier: Verifier,
) -> EvidenceVerdict:
    """Obtain a verdict. Callers must supply an explicit Verifier instance."""
    if verifier is None:
        raise VerdictRequiredError(
            "A Verifier instance is required; generation cannot decide sufficiency."
        )
    return verifier.verify(question, evidence_pack)


def require_verdict(verdict: EvidenceVerdict | None) -> EvidenceVerdict:
    """Refuse to proceed when no verdict exists yet."""
    if verdict is None:
        raise VerdictRequiredError(
            f"{INVARIANT} A verdict is required before any answer tokens."
        )
    return verdict


def _verdict_value(verdict: EvidenceVerdict | ProductVerdict) -> ProductVerdict:
    if isinstance(verdict, EvidenceVerdict):
        return verdict.verdict
    return verdict


def generation_kind(
    verdict: EvidenceVerdict | ProductVerdict,
) -> GenerationKind | None:
    """Return which generation mode is allowed, if any.

    supported -> answer generation
    conflicting -> conflict explanation (both sides; never a chosen fact)
    unsupported / ambiguous -> forbidden
    """
    value = _verdict_value(verdict)
    if value == "supported":
        return "answer"
    if value == "conflicting":
        return "conflict_explanation"
    return None


def can_generate(verdict: EvidenceVerdict | ProductVerdict) -> bool:
    """True only when some generation tokens (answer or conflict explanation) are allowed."""
    return generation_kind(verdict) is not None


def can_generate_answer(verdict: EvidenceVerdict | ProductVerdict) -> bool:
    return generation_kind(verdict) == "answer"


def can_explain_conflict(verdict: EvidenceVerdict | ProductVerdict) -> bool:
    return generation_kind(verdict) == "conflict_explanation"


def sse_token_events_allowed(verdict: EvidenceVerdict | ProductVerdict) -> bool:
    """SSE event: token is illegal unless this returns True."""
    return can_generate(verdict)


def assert_generation_allowed(
    verdict: EvidenceVerdict | ProductVerdict | None,
) -> GenerationKind:
    """Raise unless generation tokens are permitted for this verdict."""
    if verdict is None:
        raise UnsupportedAnswerTokensError(
            f"{INVARIANT} Generation is forbidden until a verdict exists."
        )
    kind = generation_kind(verdict)
    if kind is None:
        raise UnsupportedAnswerTokensError(
            f"{INVARIANT} Generation is forbidden for verdict={_verdict_value(verdict)!r}."
        )
    return kind


def assert_no_tokens_unless_allowed(
    verdict: EvidenceVerdict | ProductVerdict | None,
) -> None:
    """Testable invariant helper used by later stream-order tests."""
    if verdict is None:
        raise UnsupportedAnswerTokensError(
            f"{INVARIANT} No tokens may be emitted before a verdict exists."
        )
    if not sse_token_events_allowed(verdict):
        raise UnsupportedAnswerTokensError(
            f"{INVARIANT} SSE token events are forbidden for "
            f"verdict={_verdict_value(verdict)!r}."
        )
