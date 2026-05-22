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
        model.predict.assert_called_once()
    get_settings.cache_clear()
