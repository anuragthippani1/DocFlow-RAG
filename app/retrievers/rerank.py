from functools import lru_cache
from typing import Any

from langchain_core.documents import Document

from app.logging_utils import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _cross_encoder():
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:
        raise ImportError(
            "sentence-transformers is required when RERANK_ENABLED=true"
        ) from exc
    return CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


def rerank_documents(query: str, documents: list[Document], top_n: int) -> list[Document]:
    if not documents:
        return []
    if top_n <= 0:
        return documents

    try:
        model = _cross_encoder()
        pairs = [(query, doc.page_content) for doc in documents]
        scores = model.predict(pairs)
        ranked = sorted(zip(scores, documents), key=lambda item: float(item[0]), reverse=True)
        return [doc for _, doc in ranked[:top_n]]
    except Exception:
        logger.exception("Cross-encoder rerank failed; returning unranked documents")
        return documents[:top_n]
