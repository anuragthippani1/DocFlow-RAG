"""Evidence-first architecture contracts.

Phase 3 adds deterministic structured conflict detection after verify().
The answer generator still must not run until an evidence verdict exists.
"""

from app.evidence.pack import (
    build_evidence_pack,
    pack_to_json,
    source_details_from_pack,
)
from app.evidence.conflicts import apply_conflicts, detect_conflicts
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
    "detect_conflicts",
    "apply_conflicts",
    "generation_kind",
    "pack_to_json",
    "require_verdict",
    "source_details_from_pack",
    "sse_token_events_allowed",
    "verify",
]
