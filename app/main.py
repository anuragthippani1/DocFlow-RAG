import asyncio
import os
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Awaitable, Callable

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.responses import Response

from app.auth import APIKeyMiddleware, RateLimitMiddleware
from app.agents._common import AgentOutput, default_agent_output
from app.agents.decision_agent import generate_final_decision_async
from app.agents.external_risk_agent import analyze_external_risk_async
from app.agents.inventory_agent import analyze_inventory_async
from app.agents.logistics_agent import analyze_logistics_async
from app.agents.supplier_agent import analyze_supplier_async
from app.config import ConfigurationError, get_settings, validate_settings
from app.db_utils import vector_db_ready
from app.external_risk import fetch_external_risk_context
from app.ingest import delete_document, force_reindex, ingest_documents
from app.status import DocumentStatus, list_document_statuses, set_document_status
from app.logging_utils import get_logger
from app.observability import configure_langsmith
from app.query import build_qa_chain


load_dotenv()
configure_langsmith()

# Bump when releasing meaningful API or behavior changes.
APP_VERSION = "1.3.0"

DATA_DIR = Path("data")
logger = get_logger(__name__)
_start_time = time.time()
_query_cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
_query_count = 0
_cache_hits = 0
UPLOAD_CHUNK_SIZE = 1024 * 1024


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


def _validated_question(payload: QueryRequest) -> str:
    max_len = get_settings().max_question_length
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if len(question) > max_len:
        raise HTTPException(
            status_code=400,
            detail=f"Question exceeds maximum length of {max_len} characters.",
        )
    return question


@lru_cache(maxsize=1)
def get_qa():
    return build_qa_chain()


def _source_label(metadata: dict) -> str:
    file_name = metadata.get("file_name")
    if file_name:
        return str(file_name)
    source = str(metadata.get("source", "Unknown"))
    return Path(source).name if source not in {"", "Unknown"} else source


def _top_unique_sources(result: dict, limit: int = 2) -> list[str]:
    source_docs = result.get("source_documents") or []
    unique_sources: list[str] = []
    seen: set[str] = set()
    for doc in source_docs:
        src = _source_label(doc.metadata or {})
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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        validate_settings()
    except ConfigurationError:
        logger.exception("Application configuration is invalid")
        raise
    yield


app = FastAPI(title="DocFlow RAG API", lifespan=lifespan)
settings = get_settings()

app.add_middleware(RateLimitMiddleware, limit_per_minute=settings.rate_limit_per_minute)
app.add_middleware(APIKeyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*", "X-API-Key"],
    # So browser JS on another origin (e.g. static UI on :5500) can read custom headers.
    expose_headers=["X-Response-Time", "X-Cache"],
)

SLOW_REQUEST_THRESHOLD_MS = 5000


@app.middleware("http")
async def timing_middleware(request: Request, call_next: Callable) -> Response:
    start = time.perf_counter()
    response: Response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    response.headers["X-Response-Time"] = f"{elapsed_ms}ms"
    if elapsed_ms > SLOW_REQUEST_THRESHOLD_MS:
        logger.warning(
            "Slow request: %s %s took %.1fms", request.method, request.url.path, elapsed_ms
        )
    return response


@app.get("/health")
async def health_check():
    ready = vector_db_ready(get_settings().db_path)
    return {
        "status": "ok" if ready else "degraded",
        "service": "DocFlow RAG API",
        "version": APP_VERSION,
        "vector_db_ready": ready,
    }


@app.delete("/documents/{filename}")
async def remove_document(filename: str):
    try:
        result = await run_in_threadpool(delete_document, filename)
        get_qa.cache_clear()
        _clear_query_cache()
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Failed to delete document %s", filename)
        raise HTTPException(status_code=500, detail="Failed to delete document.")


@app.post("/documents/reindex")
async def reindex_documents():
    try:
        result = await run_in_threadpool(force_reindex)
        get_qa.cache_clear()
        _clear_query_cache()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Force re-index failed")
        raise HTTPException(status_code=500, detail="Failed to rebuild vector index.")


@app.get("/documents")
async def list_documents():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(
        f.name for f in DATA_DIR.iterdir() if f.is_file() and f.name.lower().endswith(".pdf")
    )
    return {
        "count": len(pdfs),
        "documents": pdfs,
        "statuses": list_document_statuses(),
    }


@app.get("/status")
async def ingestion_status():
    return {"documents": list_document_statuses()}


@app.get("/metrics")
async def metrics():
    uptime_seconds = round(time.time() - _start_time, 1)
    return {
        "version": APP_VERSION,
        "uptime_seconds": uptime_seconds,
        "total_queries": _query_count,
        "cache_hits": _cache_hits,
        "cache_size": len(_query_cache),
        "hybrid_retrieval_enabled": get_settings().hybrid_retrieval_enabled,
        "rerank_enabled": get_settings().rerank_enabled,
        "celery_enabled": get_settings().celery_enabled,
    }


@app.post("/cache/clear")
async def clear_cache():
    _clear_query_cache()
    logger.info("Query cache cleared via API")
    return {"message": "Query cache cleared."}


@app.get("/stats")
async def stats():
    uptime_seconds = round(time.time() - _start_time, 1)
    return {
        "version": APP_VERSION,
        "uptime_seconds": uptime_seconds,
        "total_queries": _query_count,
        "cache_hits": _cache_hits,
        "cache_size": len(_query_cache),
        "cache_max_size": get_settings().query_cache_max_size,
        "cache_enabled": get_settings().query_cache_enabled,
    }


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
    max_upload_bytes = get_settings().max_upload_size_mb * 1024 * 1024

    try:
        bytes_written = 0
        with dest_path.open("wb") as f:
            while chunk := file.file.read(UPLOAD_CHUNK_SIZE):
                bytes_written += len(chunk)
                if bytes_written > max_upload_bytes:
                    f.close()
                    dest_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"Uploaded PDF exceeds {get_settings().max_upload_size_mb} MB limit.",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to save uploaded file %s", file.filename)
        raise HTTPException(status_code=500, detail="Failed to save the uploaded file.")
    finally:
        try:
            file.file.close()
        except Exception:
            pass

    settings = get_settings()
    set_document_status(dest_path.name, DocumentStatus.QUEUED, "Upload saved")

    try:
        if settings.celery_enabled:
            from workers.tasks import ingest_document_task

            ingest_document_task.delay(dest_path.name)
            return {
                "message": "Upload queued for background ingestion.",
                "filename": dest_path.name,
                "status": DocumentStatus.QUEUED.value,
            }

        set_document_status(dest_path.name, DocumentStatus.PROCESSING, "Ingesting")
        await run_in_threadpool(ingest_documents)
        set_document_status(dest_path.name, DocumentStatus.DONE, "Ingestion completed")
        get_qa.cache_clear()
        _clear_query_cache()
    except Exception as exc:
        set_document_status(dest_path.name, DocumentStatus.FAILED, str(exc))
        logger.exception("Ingestion failed for %s", file.filename)
        raise HTTPException(
            status_code=500,
            detail="Document ingestion failed. Ensure the PDF is valid and try again.",
        )

    return {
        "message": "Upload successful. Vector DB updated.",
        "filename": dest_path.name,
        "status": DocumentStatus.DONE.value,
    }


@app.post("/query")
async def query_rag(payload: QueryRequest):
    question = _validated_question(payload)

    global _query_count, _cache_hits

    try:
        _query_count += 1

        if not vector_db_ready(get_settings().db_path):
            return JSONResponse(
                status_code=503,
                content={"error": "No vector database found. Upload documents first."},
            )

        cached = _get_cached_response(question)
        if cached:
            _cache_hits += 1
            return JSONResponse(content=cached, headers={"X-Cache": "HIT"})

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
        return JSONResponse(content=response, headers={"X-Cache": "MISS"})
    except asyncio.TimeoutError:
        logger.warning("Query timed out for: %s", question[:80])
        raise HTTPException(status_code=504, detail="Query timed out. Try a narrower question.")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Query failed")
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while processing your query. Please try again.",
        )
