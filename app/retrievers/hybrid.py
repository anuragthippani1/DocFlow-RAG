from typing import Any

from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict

from app.config import Settings
from app.evidence.pack import retriever_kind_from_flags
from app.evidence.types import RetrieverKind
from app.logging_utils import get_logger
from app.retrievers.rerank import rerank_documents

logger = get_logger(__name__)

_BACKEND_KEY = "_retrieval_backend"


def _docstore_documents(vectorstore: FAISS) -> list[Document]:
    docstore = getattr(vectorstore, "docstore", None)
    store = getattr(docstore, "_dict", None)
    if not isinstance(store, dict):
        return []
    return [doc for doc in store.values() if getattr(doc, "page_content", None)]


def _stamp_backend(documents: list[Document], backend: str) -> list[Document]:
    stamped: list[Document] = []
    for doc in documents:
        metadata = dict(getattr(doc, "metadata", None) or {})
        metadata[_BACKEND_KEY] = backend
        stamped.append(
            Document(
                page_content=str(getattr(doc, "page_content", "") or ""),
                metadata=metadata,
            )
        )
    return stamped


def _dedupe_documents(documents: list[Document]) -> list[Document]:
    seen: set[str] = set()
    unique: list[Document] = []
    for doc in documents:
        key = f"{doc.metadata.get('file_name','')}|{doc.page_content[:120]}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(doc)
    return unique


class HybridRerankRetriever(BaseRetriever):
    """FAISS + BM25 ensemble with optional cross-encoder reranking."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    vectorstore: Any
    settings: Settings
    last_retriever_kind: RetrieverKind | None = None

    def _get_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
        fetch_k = max(self.settings.retriever_fetch_k, self.settings.retriever_k)
        used_hybrid = False
        if self.settings.hybrid_retrieval_enabled:
            corpus = _docstore_documents(self.vectorstore)
            if not corpus:
                logger.warning("Hybrid retrieval enabled but docstore is empty; using FAISS only")
                docs = self.vectorstore.max_marginal_relevance_search(
                    query,
                    k=fetch_k,
                    fetch_k=fetch_k,
                    lambda_mult=0.65,
                )
                docs = _stamp_backend(docs, "mmr")
            else:
                bm25 = BM25Retriever.from_documents(corpus)
                bm25.k = self.settings.bm25_fetch_k
                faiss_retriever = self.vectorstore.as_retriever(
                    search_type="mmr",
                    search_kwargs={
                        "k": fetch_k,
                        "fetch_k": fetch_k,
                        "lambda_mult": 0.65,
                    },
                )
                hybrid = EnsembleRetriever(
                    retrievers=[faiss_retriever, bm25],
                    weights=[0.5, 0.5],
                )
                docs = hybrid.invoke(query)
                docs = _dedupe_documents(docs)
                docs = _stamp_backend(docs, "hybrid")
                used_hybrid = True
        else:
            docs = self.vectorstore.max_marginal_relevance_search(
                query,
                k=fetch_k,
                fetch_k=fetch_k,
                lambda_mult=0.65,
            )
            docs = _stamp_backend(docs, "mmr")

        reranked = False
        if self.settings.rerank_enabled:
            docs = rerank_documents(query, docs, self.settings.rerank_top_n)
            reranked = any(
                isinstance(getattr(doc, "metadata", None), dict)
                and "rerank_score" in doc.metadata
                for doc in docs
            )
        self.last_retriever_kind = retriever_kind_from_flags(
            used_hybrid=used_hybrid, reranked=reranked
        )
        return docs[: self.settings.retriever_k]


def build_retriever(vectorstore: FAISS, settings: Settings) -> BaseRetriever:
    if settings.hybrid_retrieval_enabled or settings.rerank_enabled:
        return HybridRerankRetriever(vectorstore=vectorstore, settings=settings)
    return vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={
            "k": settings.retriever_k,
            "fetch_k": settings.retriever_fetch_k,
            "lambda_mult": 0.65,
        },
    )
