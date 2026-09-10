"""Evidence-first architecture contracts.

Phase 1 adds EvidencePack construction over existing retrieval. The live
query path must not call verify() until Phase 2.
"""

from app.evidence.pack import (
    build_evidence_pack,
    pack_to_json,
    source_details_from_pack,
)
from app.evidence.types import (
    Claim,
    ClaimSupport,
    Conflict,
    ConflictKind,
    ConflictSide,
    EvidenceCoverage,
    EvidenceItem,
    EvidencePack,
    EvidenceVerdict,
    GenerationKind,
    IntentResult,
    ProductVerdict,
    Relevance,
    RetrieverKind,
    Stance,
    UnsupportedKind,
)
from app.evidence.verifier import (
    INVARIANT,
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

__all__ = [
    "INVARIANT",
    "Claim",
    "ClaimSupport",
    "Conflict",
    "ConflictKind",
    "ConflictSide",
    "EvidenceCoverage",
    "EvidenceItem",
    "EvidencePack",
    "EvidenceVerdict",
    "GenerationKind",
    "IntentResult",
    "ProductVerdict",
    "Relevance",
    "RetrieverKind",
    "Stance",
    "UnsupportedAnswerTokensError",
    "UnsupportedKind",
    "VerdictRequiredError",
    "Verifier",
    "assert_generation_allowed",
    "assert_no_tokens_unless_allowed",
    "build_evidence_pack",
    "can_explain_conflict",
    "can_generate",
    "can_generate_answer",
    "generation_kind",
    "pack_to_json",
    "require_verdict",
    "source_details_from_pack",
    "sse_token_events_allowed",
    "verify",
]
