from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from app.config import get_settings


def test_hybrid_retriever_used_when_enabled(monkeypatch):
    monkeypatch.setenv("HYBRID_RETRIEVAL_ENABLED", "true")
    monkeypatch.setenv("RERANK_ENABLED", "false")
    get_settings.cache_clear()

    settings = get_settings()
    vectorstore = MagicMock()
    doc = MagicMock()
    doc.page_content = "supply chain inventory logistics"
    doc.metadata = {"file_name": "report.pdf"}
    vectorstore.docstore._dict = {"1": doc}

    with (
        patch("app.retrievers.hybrid.BM25Retriever.from_documents") as bm25_from_docs,
        patch("app.retrievers.hybrid.EnsembleRetriever") as ensemble_cls,
    ):
        bm25 = MagicMock()
        bm25_from_docs.return_value = bm25
        ensemble = MagicMock()
        ensemble.invoke.return_value = [doc]
        ensemble_cls.return_value = ensemble
        vectorstore.as_retriever.return_value.invoke.return_value = [doc]
        vectorstore.max_marginal_relevance_search.return_value = [doc]

        from app.retrievers.hybrid import HybridRerankRetriever

        retriever = HybridRerankRetriever(vectorstore=vectorstore, settings=settings)
        docs = retriever._get_relevant_documents("inventory risk")
        assert docs
        assert retriever.last_retriever_kind == "hybrid"
        assert docs[0].metadata["_retrieval_backend"] == "hybrid"
        ensemble_cls.assert_called_once()
    get_settings.cache_clear()


def test_hybrid_falls_back_to_mmr_when_docstore_empty(monkeypatch):
    monkeypatch.setenv("HYBRID_RETRIEVAL_ENABLED", "true")
    monkeypatch.setenv("RERANK_ENABLED", "false")
    get_settings.cache_clear()

    settings = get_settings()
    vectorstore = MagicMock()
    vectorstore.docstore._dict = {}
    mmr_doc = Document(page_content="fallback chunk", metadata={"file_name": "only.pdf"})
    vectorstore.max_marginal_relevance_search.return_value = [mmr_doc]

    from app.retrievers.hybrid import HybridRerankRetriever

    retriever = HybridRerankRetriever(vectorstore=vectorstore, settings=settings)
    docs = retriever._get_relevant_documents("inventory risk")
    assert docs
    assert retriever.last_retriever_kind == "mmr"
    assert docs[0].metadata["_retrieval_backend"] == "mmr"
    vectorstore.max_marginal_relevance_search.assert_called_once()
    get_settings.cache_clear()
