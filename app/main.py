import asyncio
import os
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agents._common import AgentOutput, default_agent_output
from app.agents.decision_agent import generate_final_decision
from app.agents.external_risk_agent import analyze_external_risk
from app.agents.inventory_agent import analyze_inventory
from app.agents.logistics_agent import analyze_logistics
from app.agents.supplier_agent import analyze_supplier
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


async def _run_agent(
    name: str, analyzer: Callable[[str], AgentOutput], answer: str
) -> AgentOutput:
    try:
        return await run_in_threadpool(analyzer, answer)
    except Exception as e:
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
        supplier, inventory, logistics, external_risk = await asyncio.gather(
            _run_agent("Supplier Agent", analyze_supplier, answer),
            _run_agent("Inventory Agent", analyze_inventory, answer),
            _run_agent("Logistics Agent", analyze_logistics, answer),
            _run_agent("External Risk Agent", analyze_external_risk, answer),
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
        decision = await run_in_threadpool(generate_final_decision, decision_inputs)
        sources = _top_unique_sources(result, limit=2)
        return {
            "answer": answer,
            "agents": agents,
            "decision": decision,
            "sources": sources,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
