"""Conversational RAG: condense follow-ups, retrieve, generate, and stream."""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from typing import Any, AsyncIterator, Iterable

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import Settings, get_settings, openrouter_headers
from app.evidence.pack import (
    build_evidence_pack,
    infer_retriever_kind,
    source_details_from_pack,
)
from app.evidence.types import EvidencePack, RetrieverKind
from app.logging_utils import get_logger
from app.retrievers import build_retriever

logger = get_logger(__name__)

_CONDENSE_PROMPT = """Rewrite the latest user question as a standalone search query for a document index.
Use the conversation only to resolve references like "it", "that", "which one", or "those".
Return only the rewritten query, with no quotes or preamble.

Conversation:
{history}

Latest question:
{question}
"""

_ANSWER_SYSTEM = """You are DocRAGFlow, a document-grounded assistant.
Answer using only the numbered excerpts below. If they do not contain the answer, say so.
When a claim comes from an excerpt, cite it as [1], [2], etc. matching the excerpt number.
Do not invent documents, page numbers, or citations.
Prefer concise, well-structured answers. Use Markdown when it helps readability.

Retrieved excerpts:
{context}
"""


@lru_cache(maxsize=1)
def _embeddings():
    settings = get_settings()
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base,
        default_headers=openrouter_headers(),
    )


@lru_cache(maxsize=1)
def _vectorstore():
    settings = get_settings()
    return FAISS.load_local(
        settings.db_path, _embeddings(), allow_dangerous_deserialization=True
    )


def clear_retriever_cache() -> None:
    _embeddings.cache_clear()
    _vectorstore.cache_clear()


def _llm(*, streaming: bool = False) -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.qa_model,
        temperature=0,
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base,
        default_headers=openrouter_headers(),
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
        streaming=streaming,
    )


def product_retrieval_settings(settings: Settings | None = None) -> Settings:
    """Product chat path always attempts hybrid retrieval then rerank."""
    current = settings or get_settings()
    return replace(current, hybrid_retrieval_enabled=True, rerank_enabled=True)


def source_details(docs: Iterable[Document], limit: int | None = None) -> list[dict[str, Any]]:
    selected = list(docs)
    if limit is not None:
        selected = selected[:limit]
    pack = build_evidence_pack(query="", standalone_query="", documents=selected)
    return source_details_from_pack(pack)


def unique_source_names(details: list[dict[str, Any]], limit: int) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in details:
        name = item.get("document")
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
        if len(names) >= limit:
            break
    return names


def _format_history(history: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for item in history:
        role = "User" if item.get("role") == "user" else "Assistant"
        content = " ".join(str(item.get("content") or "").split())
        if not content:
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(none)"


def condense_question(question: str, history: list[dict[str, str]]) -> str:
    if not history:
        return question
    prompt = _CONDENSE_PROMPT.format(history=_format_history(history), question=question)
    try:
        response = _llm(streaming=False).invoke([HumanMessage(content=prompt)])
        rewritten = str(getattr(response, "content", "") or "").strip()
        return rewritten or question
    except Exception:
        logger.exception("Failed to condense follow-up question")
        return question


def retrieve_documents(query: str) -> list[Document]:
    docs, _kind = retrieve_for_pack(query)
    return docs


def retrieve_for_pack(query: str) -> tuple[list[Document], RetrieverKind]:
    """Run the existing retriever/reranker; do not retrieve a second time later."""
    retriever = build_retriever(_vectorstore(), product_retrieval_settings())
    docs = list(retriever.invoke(query) or [])
    kind = getattr(retriever, "last_retriever_kind", None)
    return docs, infer_retriever_kind(docs, last_retriever_kind=kind)


def _context_block(details: list[dict[str, Any]]) -> str:
    if not details:
        return "(no excerpts retrieved)"
    blocks = []
    for item in details:
        page = f", page {item['page']}" if item.get("page") is not None else ""
        blocks.append(f"[{item['n']}] {item['document']}{page}\n{item.get('excerpt') or ''}")
    return "\n\n".join(blocks)


def build_chat_messages(
    question: str,
    history: list[dict[str, str]],
    details: list[dict[str, Any]],
) -> list:
    messages: list = [
        SystemMessage(content=_ANSWER_SYSTEM.format(context=_context_block(details)))
    ]
    for item in history:
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if item.get("role") == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    messages.append(HumanMessage(content=question.strip()))
    return messages


def _chunk_text(chunk: Any) -> str:
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return str(content or "")


def generate_answer(
    question: str, history: list[dict[str, str]], details: list[dict[str, Any]]
) -> str:
    messages = build_chat_messages(question, history, details)
    response = _llm(streaming=False).invoke(messages)
    return str(getattr(response, "content", "") or "").strip()


async def astream_answer(
    question: str, history: list[dict[str, str]], details: list[dict[str, Any]]
) -> AsyncIterator[str]:
    messages = build_chat_messages(question, history, details)
    async for chunk in _llm(streaming=True).astream(messages):
        text = _chunk_text(chunk)
        if text:
            yield text


def run_conversational_retrieval(
    question: str, history: list[dict[str, str]]
) -> tuple[str, list[Document], list[dict[str, Any]], EvidencePack]:
    standalone = condense_question(question, history)
    docs, retriever_kind = retrieve_for_pack(standalone)
    pack = build_evidence_pack(
        query=question,
        standalone_query=standalone,
        documents=docs,
        retriever=retriever_kind,
    )
    details = source_details_from_pack(pack)
    return standalone, docs, details, pack
