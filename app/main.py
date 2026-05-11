import asyncio
import os
import shutil
import time
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import Any, Awaitable, Callable

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agents._common import AgentOutput, default_agent_output
from app.agents.decision_agent import generate_final_decision_async
from app.agents.external_risk_agent import analyze_external_risk_async
from app.agents.inventory_agent import analyze_inventory_async
from app.agents.logistics_agent import analyze_logistics_async
from app.agents.supplier_agent import analyze_supplier_async
from app.config import get_settings
from app.external_risk import fetch_external_risk_context
from app.ingest import ingest_documents
from app.logging_utils import get_logger
from app.query import build_qa_chain


load_dotenv()

DATA_DIR = Path("data")
logger = get_logger(__name__)
_query_cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()


class QueryRequest(BaseModel):
    question: str


@lru_cache(maxsize=1)
def get_qa():
    return build_qa_chain()


def _top_unique_sources(result: dict, limit: int = 2) -> list[str]:
    source_docs = result.get("source_documents") or []
    unique_sources: list[str] = []
    seen: set[str] = set()
    for doc in source_docs:
        src = doc.metadata.get("source", "Unknown")
        if src in seen:
            continue
        seen.add(src)
        unique_sources.append(src)
        if len(unique_sources) >= limit:
            break
    return unique_sources


def _normalize_question(question: str) -> str:
    return " ".join(question.strip().lower().split())


def _get_cached_response(question: str) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.query_cache_enabled:
        return None

    key = _normalize_question(question)
    cached = _query_cache.get(key)
    if not cached:
        return None

    _query_cache.move_to_end(key)
    logger.info("Query cache hit")
    return cached[1]


def _set_cached_response(question: str, response: dict[str, Any]) -> None:
    settings = get_settings()
    if not settings.query_cache_enabled:
        return

    key = _normalize_question(question)
    _query_cache[key] = (time.time(), response)
    _query_cache.move_to_end(key)
    while len(_query_cache) > settings.query_cache_max_size:
        _query_cache.popitem(last=False)


def _clear_query_cache() -> None:
    _query_cache.clear()


async def _run_agent(
    name: str, analyzer: Callable[[], Awaitable[AgentOutput]]
) -> AgentOutput:
    try:
        return await analyzer()
    except Exception as e:
        logger.exception("%s failed during orchestration", name)
        return default_agent_output(f"{name} failed to analyze the answer: {e}")


app = FastAPI(title="DocFlow RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "DocFlow RAG API"}


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported.")

    content_type = (file.content_type or "").lower()
    if content_type and content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = DATA_DIR / os.path.basename(file.filename)

    try:
        with dest_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")
    finally:
        try:
            file.file.close()
        except Exception:
            pass

    try:
        # Ingestion can be CPU/network heavy; avoid blocking the event loop.
        await run_in_threadpool(ingest_documents)
        # Vector DB changed; rebuild the cached chain on next query.
        get_qa.cache_clear()
        _clear_query_cache()
    except Exception as e:
        logger.exception("Ingestion failed")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")

    return {"message": "Upload successful. Vector DB updated.", "filename": dest_path.name}


@app.post("/query")
async def query_rag(payload: QueryRequest):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        cached = _get_cached_response(question)
        if cached:
            return cached

        settings = get_settings()
        qa = get_qa()
        result = await asyncio.wait_for(
            run_in_threadpool(qa.invoke, {"query": question}),
            timeout=settings.query_timeout_seconds,
        )
        answer = str(result.get("result", "")).strip()
        sources = _top_unique_sources(result, limit=settings.source_limit)
        if not answer or not sources:
            answer = answer or "No relevant document context was found for this question."

        external_context = await fetch_external_risk_context(question)
        supplier, inventory, logistics, external_risk = await asyncio.gather(
            _run_agent("Supplier Agent", lambda: analyze_supplier_async(answer)),
            _run_agent("Inventory Agent", lambda: analyze_inventory_async(answer)),
            _run_agent("Logistics Agent", lambda: analyze_logistics_async(answer)),
            _run_agent(
                "External Risk Agent",
                lambda: analyze_external_risk_async(answer, external_context),
            ),
        )
        agents: dict[str, AgentOutput] = {
            "supplier": supplier,
            "inventory": inventory,
            "logistics": logistics,
            "external_risk": external_risk,
        }
        decision_inputs: list[dict[str, Any]] = [
            {"agent": agent_name, **agent_output}
            for agent_name, agent_output in agents.items()
        ]
        decision = await generate_final_decision_async(decision_inputs)
        response = {
            "answer": answer,
            "agents": agents,
            "decision": decision,
            "sources": sources,
        }
        _set_cached_response(question, response)
        return response
    except asyncio.TimeoutError:
        logger.warning("Query timed out")
        raise HTTPException(status_code=504, detail="Query timed out. Try a narrower question.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
