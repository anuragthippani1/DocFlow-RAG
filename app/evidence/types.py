"""Evidence-first data contracts.

These models are the shared vocabulary for later phases. They do not
perform retrieval, verification, or generation on their own.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ProductVerdict = Literal["supported", "unsupported", "conflicting", "ambiguous"]
UnsupportedKind = Literal["none", "no_relevant_evidence", "insufficient_evidence"]
Relevance = Literal["relevant", "not_relevant", "uncertain"]
Stance = Literal["supports", "unused", "contradicts", "unknown"]
ClaimSupport = Literal["entailed", "insufficient", "contradicted"]
ConflictKind = Literal[
    "duration",
    "quantity",
    "percentage",
    "date",
    "price",
    "status",
    "named_attribute",
]
RetrieverKind = Literal["mmr", "hybrid", "hybrid_rerank"]
GenerationKind = Literal["answer", "conflict_explanation"]


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IntentResult(EvidenceModel):
    needs_clarification: bool
    clarification_question: str | None = None
    slots: list[str] = Field(default_factory=list)


class EvidenceItem(EvidenceModel):
    id: str
    n: int
    document: str
    page: int | None = None
    excerpt: str
    excerpt_full: str
    chunk_start_index: int | None = None
    file_mtime_ns: int | None = None
    retrieval_rank: int
    # Present only when a reranker actually scored this item. Never default to 0.
    rerank_score: float | None = None
    relevance: Relevance
    stance: Stance


class EvidencePack(EvidenceModel):
    query: str
    standalone_query: str
    retriever: RetrieverKind
    items: list[EvidenceItem] = Field(default_factory=list)


class EvidenceCoverage(EvidenceModel):
    retrieved: int
    relevant: int
    supporting: int
    unused: int
    contradicting: int
    uncertain: int
    note: str = ""


class Claim(EvidenceModel):
    id: str
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    support: ClaimSupport
    citations: list[int] = Field(default_factory=list)


class ConflictSide(EvidenceModel):
    evidence_id: str
    document: str
    page: int | None = None
    span: str
    value: str


class Conflict(EvidenceModel):
    id: str
    slot: str
    kind: ConflictKind
    sides: list[ConflictSide]
    summary: str


class EvidenceVerdict(EvidenceModel):
    verdict: ProductVerdict
    unsupported_kind: UnsupportedKind
    reason: str
    coverage: EvidenceCoverage
    evidence_ids: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    clarification_question: str | None = None

    @model_validator(mode="after")
    def _unsupported_kind_matches_verdict(self) -> EvidenceVerdict:
        if self.verdict == "unsupported":
            if self.unsupported_kind == "none":
                raise ValueError(
                    "unsupported verdict requires unsupported_kind of "
                    "no_relevant_evidence or insufficient_evidence"
                )
        elif self.unsupported_kind != "none":
            raise ValueError(
                "unsupported_kind must be 'none' unless verdict is unsupported"
            )
        return self
