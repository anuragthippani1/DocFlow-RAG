"""Convert retrieved LangChain documents into a canonical EvidencePack.

This module does not retrieve or rerank. It only represents documents already
returned by the existing retriever/reranker.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from langchain_core.documents import Document

from app.evidence.types import EvidenceItem, EvidencePack, RetrieverKind

EXCERPT_LIMIT = 320
_BACKEND_KEY = "_retrieval_backend"
_RERANK_KEY = "rerank_score"


def document_label(metadata: dict[str, Any] | None) -> str:
    metadata = metadata or {}
    file_name = metadata.get("file_name")
    if file_name:
        return str(file_name)
    source = str(metadata.get("source", "Unknown"))
    return Path(source).name if source not in {"", "Unknown"} else source


def page_number(metadata: dict[str, Any] | None) -> int | None:
    metadata = metadata or {}
    raw = metadata.get("page_number", metadata.get("page"))
    try:
        page = int(raw)
    except (TypeError, ValueError):
        return None
    # PyPDFLoader stores 0-based pages.
    return page + 1 if page >= 0 else None


def short_excerpt(text: str, limit: int = EXCERPT_LIMIT) -> str:
    excerpt = " ".join(str(text or "").split())
    if len(excerpt) > limit:
        return excerpt[: limit - 3].rstrip() + "…"
    return excerpt


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def actual_rerank_score(metadata: dict[str, Any] | None) -> float | None:
    """Return a rerank score only when one was actually stored on the document."""
    metadata = metadata or {}
    if _RERANK_KEY not in metadata:
        return None
    raw = metadata.get(_RERANK_KEY)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def infer_retriever_kind(
    documents: Iterable[Document],
    *,
    last_retriever_kind: RetrieverKind | None = None,
) -> RetrieverKind:
    if last_retriever_kind in {"mmr", "hybrid", "hybrid_rerank"}:
        return last_retriever_kind
    docs = list(documents)
    backends = {
        str((doc.metadata or {}).get(_BACKEND_KEY))
        for doc in docs
        if (doc.metadata or {}).get(_BACKEND_KEY)
    }
    has_rerank = any(actual_rerank_score(doc.metadata) is not None for doc in docs)
    used_hybrid = "hybrid" in backends
    if used_hybrid and has_rerank:
        return "hybrid_rerank"
    if used_hybrid:
        return "hybrid"
    return "mmr"


def retriever_kind_from_flags(*, used_hybrid: bool, reranked: bool) -> RetrieverKind:
    if used_hybrid and reranked:
        return "hybrid_rerank"
    if used_hybrid:
        return "hybrid"
    return "mmr"


def source_details_from_pack(pack: EvidencePack) -> list[dict[str, Any]]:
    """Backward-compatible source_details derived from EvidencePack.items."""
    details: list[dict[str, Any]] = []
    for item in pack.items:
        row: dict[str, Any] = {
            "n": item.n,
            "document": item.document,
            "excerpt": item.excerpt,
        }
        if item.page is not None:
            row["page"] = item.page
        details.append(row)
    return details


def build_evidence_pack(
    *,
    query: str,
    standalone_query: str,
    documents: Iterable[Document],
    retriever: RetrieverKind | None = None,
) -> EvidencePack:
    docs = list(documents)
    kind = infer_retriever_kind(docs, last_retriever_kind=retriever)
    items: list[EvidenceItem] = []
    for rank, doc in enumerate(docs, start=1):
        metadata = dict(getattr(doc, "metadata", None) or {})
        full = " ".join(str(getattr(doc, "page_content", "") or "").split())
        items.append(
            EvidenceItem(
                id=f"e{rank}",
                n=rank,
                document=document_label(metadata),
                page=page_number(metadata),
                excerpt=short_excerpt(full),
                excerpt_full=full,
                chunk_start_index=_optional_int(metadata.get("start_index")),
                file_mtime_ns=_optional_int(metadata.get("file_mtime_ns")),
                retrieval_rank=rank,
                rerank_score=actual_rerank_score(metadata),
                relevance="uncertain",
                stance="unknown",
            )
        )
    return EvidencePack(
        query=query,
        standalone_query=standalone_query,
        retriever=kind,
        items=items,
    )


def pack_to_json(pack: EvidencePack) -> dict[str, Any]:
    """Serialize a pack for API responses, omitting absent optional scores."""
    return pack.model_dump(mode="json", exclude_none=True)
