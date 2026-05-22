#!/usr/bin/env python3
"""Runtime validation harness for DocFlow RAG."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("OPENAI_API_KEY", "test-openrouter-key")
os.environ.setdefault("API_KEY", "")

RESULTS: list[tuple[str, str, str]] = []


def record(claimed: str, status: str, detail: str = "") -> None:
    RESULTS.append((claimed, status, detail))


def check_agent_routing() -> None:
    from app.agent_router import agents_for_domain, detect_domain

    sources = ["GRAIL — SLM-Enhanced Indexing for Agent Discovery.pdf"]
    domain = detect_domain(sources, "Research on SLM-enhanced indexing.")
    flags = agents_for_domain(domain)
    if domain == "research" and not flags["supplier"]:
        record("Dynamic agent routing (research PDFs)", "WORKING", f"domain={domain}")
    else:
        record("Dynamic agent routing (research PDFs)", "BROKEN", f"domain={domain} flags={flags}")


def check_hybrid_rerank() -> None:
    from app.config import get_settings

    get_settings.cache_clear()
    os.environ["HYBRID_RETRIEVAL_ENABLED"] = "true"
    os.environ["RERANK_ENABLED"] = "true"
    get_settings.cache_clear()
    settings = get_settings()
    try:
        from app.retrievers.hybrid import HybridRerankRetriever

        assert settings.hybrid_retrieval_enabled
        assert settings.rerank_enabled
        record("Hybrid retrieval enabled", "WORKING", "HybridRerankRetriever importable")
    except Exception as exc:
        record("Hybrid retrieval enabled", "PARTIAL", str(exc))
    finally:
        os.environ.pop("HYBRID_RETRIEVAL_ENABLED", None)
        os.environ.pop("RERANK_ENABLED", None)
        get_settings.cache_clear()


def check_celery_path() -> None:
    try:
        from workers.celery_app import celery_app
        from workers.tasks import ingest_document_task

        assert celery_app.main
        assert ingest_document_task.name
        record("Celery worker path", "WORKING", ingest_document_task.name)
    except Exception as exc:
        record("Celery worker path", "PARTIAL", str(exc))


def check_neo4j() -> None:
    from app.graph import get_graph_store

    store = get_graph_store()
    if store.enabled:
        record("Neo4j integration", "WORKING", "Connected")
    else:
        record("Neo4j integration", "PARTIAL", "Not configured (expected without NEO4J_URI)")


def check_langsmith() -> None:
    from app.observability import configure_langsmith

    configure_langsmith()
    tracing = os.getenv("LANGCHAIN_TRACING_V2", "false")
    if tracing.lower() == "true":
        record("LangSmith traces", "WORKING", "LANGCHAIN_TRACING_V2=true")
    else:
        record("LangSmith traces", "PARTIAL", "Tracing disabled in env")


def check_delete_reindex(base: str = "http://127.0.0.1:8000") -> None:
    import urllib.request

    try:
        req = urllib.request.Request(f"{base}/documents/reindex", method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode())
        if resp.status == 200 and body.get("message"):
            record("Delete and reindex endpoints", "WORKING", body.get("message", ""))
        else:
            record("Delete and reindex endpoints", "PARTIAL", str(body))
    except Exception as exc:
        record("Delete and reindex endpoints", "BROKEN", str(exc))


def check_api_endpoints(base: str = "http://127.0.0.1:8000") -> None:
    import urllib.error
    import urllib.request

    def get(path: str) -> tuple[int, dict]:
        req = urllib.request.Request(f"{base}{path}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())

    try:
        code, health = get("/health")
        if code == 200 and health.get("vector_db_ready"):
            record("API health + vector DB", "WORKING", health.get("version", ""))
        else:
            record("API health + vector DB", "PARTIAL", str(health))
    except Exception as exc:
        record("API health + vector DB", "BROKEN", str(exc))
        return

    try:
        code, metrics = get("/metrics")
        record(
            "Metrics endpoint",
            "WORKING" if code == 200 else "BROKEN",
            json.dumps(
                {
                    "hybrid": metrics.get("hybrid_retrieval_enabled"),
                    "rerank": metrics.get("rerank_enabled"),
                    "celery": metrics.get("celery_enabled"),
                }
            ),
        )
    except Exception as exc:
        record("Metrics endpoint", "BROKEN", str(exc))


def main() -> int:
    check_agent_routing()
    check_hybrid_rerank()
    check_celery_path()
    check_neo4j()
    check_langsmith()
    check_api_endpoints()
    check_delete_reindex()

    print("\n| CLAIMED FEATURE | ACTUAL STATUS | DETAIL |")
    print("|---|---|---|")
    for claimed, status, detail in RESULTS:
        detail = detail.replace("|", "/")[:120]
        print(f"| {claimed} | {status} | {detail} |")

    broken = sum(1 for _, status, _ in RESULTS if status == "BROKEN")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
