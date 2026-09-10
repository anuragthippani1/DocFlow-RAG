from unittest.mock import MagicMock, patch

from langchain_core.documents import Document


def test_rerank_executes_when_enabled(monkeypatch):
    monkeypatch.setenv("RERANK_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()

    docs = [Document(page_content="alpha"), Document(page_content="beta")]
    with patch("app.retrievers.rerank._cross_encoder") as mock_encoder:
        model = MagicMock()
        model.predict.return_value = [0.9, 0.1]
        mock_encoder.return_value = model

        from app.retrievers.rerank import rerank_documents

        result = rerank_documents("query", docs, top_n=1)
        assert len(result) == 1
        assert result[0].page_content == "alpha"
        assert result[0].metadata["rerank_score"] == 0.9
        assert "rerank_score" not in (docs[1].metadata or {})
        model.predict.assert_called_once()
    get_settings.cache_clear()


def test_rerank_failure_does_not_fabricate_scores():
    docs = [Document(page_content="alpha", metadata={"file_name": "a.pdf"})]
    with patch("app.retrievers.rerank._cross_encoder", side_effect=RuntimeError("offline")):
        from app.retrievers.rerank import rerank_documents

        result = rerank_documents("query", docs, top_n=1)
        assert len(result) == 1
        assert "rerank_score" not in (result[0].metadata or {})
