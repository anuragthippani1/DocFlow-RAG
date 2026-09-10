"""Phase 1: EvidencePack is a representation of existing retrieval results."""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.documents import Document

from app.config import get_settings
from app.evidence.pack import (
    build_evidence_pack,
    pack_to_json,
    source_details_from_pack,
)
from app.rag_chat import product_retrieval_settings, run_conversational_retrieval


def _doc(**overrides) -> Document:
    metadata = {
        "file_name": "policy.pdf",
        "page_number": 0,
        "start_index": 12,
        "file_mtime_ns": 99,
        "_retrieval_backend": "hybrid",
        "rerank_score": 0.81,
    }
    metadata.update(overrides.pop("metadata_update", {}))
    if "rerank_score" in overrides:
        score = overrides.pop("rerank_score")
        if score is None:
            metadata.pop("rerank_score", None)
        else:
            metadata["rerank_score"] = score
    content = overrides.pop("page_content", "Delivery takes 12 days from confirmation.")
    metadata.update(overrides)
    return Document(page_content=content, metadata=metadata)


def test_evidence_pack_shape_and_stable_ids():
    docs = [
        _doc(),
        _doc(
            file_name="alt.pdf",
            page_number=2,
            start_index=40,
            rerank_score=0.2,
            page_content="Delivery takes 19 days.",
        ),
    ]
    pack = build_evidence_pack(
        query="What is the delivery time?",
        standalone_query="supplier delivery time",
        documents=docs,
        retriever="hybrid_rerank",
    )
    assert pack.query == "What is the delivery time?"
    assert pack.standalone_query == "supplier delivery time"
    assert pack.retriever == "hybrid_rerank"
    assert [item.id for item in pack.items] == ["e1", "e2"]
    assert [item.n for item in pack.items] == [1, 2]
    assert [item.retrieval_rank for item in pack.items] == [1, 2]
    assert pack.items[0].n == pack.items[0].retrieval_rank == 1
    assert pack.items[0].page == 1
    assert pack.items[0].chunk_start_index == 12
    assert pack.items[0].file_mtime_ns == 99
    assert pack.items[0].excerpt_full.startswith("Delivery takes 12 days")
    assert pack.items[0].relevance == "uncertain"
    assert pack.items[0].stance == "unknown"
    assert pack.items[0].rerank_score == 0.81


def test_source_details_are_mapped_from_pack_items():
    pack = build_evidence_pack(
        query="q",
        standalone_query="q",
        documents=[_doc(), _doc(file_name="other.pdf", page_number=4)],
        retriever="hybrid_rerank",
    )
    details = source_details_from_pack(pack)
    assert details[0] == {
        "n": 1,
        "document": "policy.pdf",
        "excerpt": pack.items[0].excerpt,
        "page": 1,
    }
    assert set(details[0]) <= {"n", "document", "page", "excerpt"}
    assert details[1]["document"] == "other.pdf"
    assert details[1]["n"] == 2


def test_rerank_score_omitted_when_missing_and_not_fabricated():
    pack = build_evidence_pack(
        query="q",
        standalone_query="q",
        documents=[_doc(rerank_score=None, metadata_update={"_retrieval_backend": "hybrid"})],
        retriever="hybrid",
    )
    assert pack.items[0].rerank_score is None
    dumped = pack_to_json(pack)
    assert "rerank_score" not in dumped["items"][0]
    assert dumped["items"][0]["stance"] == "unknown"
    assert dumped["items"][0]["relevance"] == "uncertain"
    assert "confidence" not in dumped["items"][0]


def test_retriever_kind_hybrid_without_scores():
    pack = build_evidence_pack(
        query="q",
        standalone_query="q",
        documents=[_doc(rerank_score=None)],
    )
    assert pack.retriever == "hybrid"


def test_retriever_kind_hybrid_rerank_when_scores_present():
    pack = build_evidence_pack(
        query="q",
        standalone_query="q",
        documents=[_doc(rerank_score=0.4)],
    )
    assert pack.retriever == "hybrid_rerank"


def test_retriever_kind_mmr_without_hybrid_backend():
    pack = build_evidence_pack(
        query="q",
        standalone_query="q",
        documents=[_doc(rerank_score=None, metadata_update={"_retrieval_backend": "mmr"})],
    )
    assert pack.retriever == "mmr"


def test_product_path_enables_hybrid_and_rerank_even_if_flags_are_off(monkeypatch):
    monkeypatch.setenv("HYBRID_RETRIEVAL_ENABLED", "false")
    monkeypatch.setenv("RERANK_ENABLED", "false")
    get_settings.cache_clear()
    settings = product_retrieval_settings()
    assert settings.hybrid_retrieval_enabled is True
    assert settings.rerank_enabled is True
    assert get_settings().hybrid_retrieval_enabled is False
    assert get_settings().rerank_enabled is False
    get_settings.cache_clear()


def test_run_conversational_retrieval_builds_pack_from_retrieved_docs(monkeypatch):
    docs = [_doc(), _doc(file_name="b.pdf", rerank_score=0.1, page_content="Other fact.")]
    monkeypatch.setattr(
        "app.rag_chat.condense_question", lambda question, history: "standalone q"
    )
    monkeypatch.setattr(
        "app.rag_chat.retrieve_for_pack",
        lambda query: (docs, "hybrid_rerank"),
    )
    standalone, returned_docs, details, pack = run_conversational_retrieval(
        "What is the delivery time?", []
    )
    assert standalone == "standalone q"
    assert returned_docs == docs
    assert pack.retriever == "hybrid_rerank"
    assert [item.id for item in pack.items] == ["e1", "e2"]
    assert details == source_details_from_pack(pack)
    assert details[0]["n"] == 1
    assert details[0]["document"] == "policy.pdf"
    assert "excerpt" in details[0]


def test_retrieve_for_pack_does_not_retrieve_twice(monkeypatch):
    calls = {"count": 0}

    class FakeRetriever:
        last_retriever_kind = "hybrid_rerank"

        def invoke(self, query):
            calls["count"] += 1
            return [_doc()]

    monkeypatch.setattr("app.rag_chat._vectorstore", lambda: MagicMock())
    monkeypatch.setattr("app.rag_chat.build_retriever", lambda vs, settings: FakeRetriever())
    monkeypatch.setattr(
        "app.rag_chat.condense_question", lambda question, history: question
    )
    run_conversational_retrieval("delivery time?", [])
    assert calls["count"] == 1
