"""Shared evidence-first test fixtures. Not end-to-end LLM results."""

from __future__ import annotations

from langchain_core.documents import Document

from app.evidence.answerability import apply_safety_rules, relabel_pack
from app.evidence.pack import build_evidence_pack, source_details_from_pack
from app.evidence.types import EvidencePack, IntentResult


def document_pack(
    question: str,
    text: str,
    *,
    document: str = "supplier.pdf",
    retriever: str = "hybrid_rerank",
    page_number: int = 0,
) -> EvidencePack:
    return documents_pack(
        question,
        [(document, text, page_number)],
        retriever=retriever,
    )


def documents_pack(
    question: str,
    excerpts: list[tuple[str, str] | tuple[str, str, int]],
    *,
    retriever: str = "hybrid_rerank",
) -> EvidencePack:
    documents = []
    for entry in excerpts:
        document, text = entry[0], entry[1]
        page_number = entry[2] if len(entry) == 3 else 0
        documents.append(
            Document(
                page_content=text,
                metadata={
                    "file_name": document,
                    "page_number": page_number,
                    "_retrieval_backend": "hybrid",
                    "rerank_score": 0.8,
                },
            )
        )
    return build_evidence_pack(
        query=question,
        standalone_query=question,
        documents=documents,
        retriever=retriever,  # type: ignore[arg-type]
    )


def supported_outcome(pack: EvidencePack):
    labels = {item.id: ("relevant", "supports") for item in pack.items}
    labeled = relabel_pack(pack, labels) if labels else pack
    verdict = apply_safety_rules(
        labeled,
        condition="supported_evidence",
        reason="The retrieved excerpt answers the question.",
    )
    return labeled, verdict


def unsupported_outcome(pack: EvidencePack, *, kind: str, reason: str):
    if kind == "no_relevant_evidence":
        labels = {item.id: ("not_relevant", "unused") for item in pack.items}
        condition = "no_relevant_evidence"
    else:
        labels = {item.id: ("relevant", "unknown") for item in pack.items}
        condition = "insufficient_evidence"
    labeled = relabel_pack(pack, labels) if labels else pack
    verdict = apply_safety_rules(labeled, condition=condition, reason=reason)
    return labeled, verdict


def clear_intent(_question: str, _history: list | None = None) -> IntentResult:
    return IntentResult(needs_clarification=False, clarification_question=None, slots=[])


def patch_evidence_path(
    monkeypatch,
    main,
    *,
    pack: EvidencePack,
    verify_fn,
    answer: str = "Generated answer [1].",
    generate_calls: list | None = None,
    stream_calls: list | None = None,
):
    details = source_details_from_pack(pack)
    monkeypatch.setattr(main, "analyze_intent", clear_intent)
    monkeypatch.setattr(
        main,
        "run_conversational_retrieval",
        lambda question, history: (question, [], details, pack),
    )
    monkeypatch.setattr(main, "verify_evidence", verify_fn)

    def _generate(*_args, **_kwargs):
        if generate_calls is not None:
            generate_calls.append("generate")
        return answer

    async def _stream(*_args, **_kwargs):
        if stream_calls is not None:
            stream_calls.append("stream")
        yield answer

    monkeypatch.setattr(main, "generate_answer", _generate)
    monkeypatch.setattr(main, "astream_answer", _stream)
    return details
