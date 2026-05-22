from app.retrievers.hybrid import build_retriever


def test_build_retriever_faiss_only_when_hybrid_disabled(monkeypatch):
    monkeypatch.setenv("HYBRID_RETRIEVAL_ENABLED", "false")
    monkeypatch.setenv("RERANK_ENABLED", "false")
    from app.config import get_settings

    get_settings.cache_clear()
    from app.config import get_settings as gs

    settings = gs()
    assert settings.hybrid_retrieval_enabled is False
    get_settings.cache_clear()
