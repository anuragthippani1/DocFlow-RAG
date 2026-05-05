import os
import shutil
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.ingest import ingest_documents
from app.query import build_qa_chain


load_dotenv()

DATA_DIR = Path("data")


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


app = FastAPI(title="DocFlow RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported.")

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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")

    return {"message": "Upload successful. Vector DB updated.", "filename": dest_path.name}


@app.post("/query")
async def query_rag(payload: QueryRequest):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        qa = get_qa()
        result = await run_in_threadpool(qa.invoke, {"query": question})
        answer = str(result.get("result", "")).strip()
        sources = _top_unique_sources(result, limit=2)
        return {"answer": answer, "sources": sources}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
