import json
import os
import re
from typing import Any, Literal, TypedDict, cast

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


load_dotenv()

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
RiskLevel = Literal["Low", "Medium", "High"]


class AnalysisResult(TypedDict):
    summary: str
    key_insight: str
    risk_level: RiskLevel
    recommendation: str


def _openrouter_headers() -> dict[str, str]:
    return {
        "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", ""),
        "X-Title": os.getenv("OPENROUTER_APP_NAME", "DocFlow-RAG"),
    }


def _openai_compatible_base_url() -> str:
    return os.getenv("OPENAI_API_BASE", DEFAULT_OPENROUTER_BASE_URL)


def _build_analyzer_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("AGENT_MODEL", "gpt-3.5-turbo"),
        temperature=0,
        base_url=_openai_compatible_base_url(),
        default_headers=_openrouter_headers(),
    )


def _coerce_risk_level(value: Any) -> RiskLevel:
    v = str(value).strip().lower()
    if v == "high":
        return "High"
    if v == "medium":
        return "Medium"
    return "Low"


def _default_result() -> AnalysisResult:
    return {
        "summary": "",
        "key_insight": "",
        "risk_level": "Low",
        "recommendation": "",
    }


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """
    Best-effort extraction of a single JSON object from an LLM response.
    Keeps the main function resilient to occasional formatting drift.
    """
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return cast(dict[str, Any], parsed)
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None

    try:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return cast(dict[str, Any], parsed)
    except Exception:
        return None

    return None


def analyze_response(rag_answer: str) -> AnalysisResult:
    """
    Analyze a RAG answer and return a structured, JSON-like dict:
    - summary
    - key_insight
    - risk_level (Low/Medium/High)
    - recommendation
    """
    answer = (rag_answer or "").strip()
    if not answer:
        return _default_result()

    llm = _build_analyzer_llm()

    prompt = (
        "You are an analyst. Read the RAG answer and produce a STRICT JSON object.\n"
        "Rules:\n"
        "- Output ONLY valid JSON (no markdown, no code fences, no extra text)\n"
        '- risk_level must be one of: "Low", "Medium", "High"\n'
        "- Keep fields concise but informative.\n\n"
        "RAG_ANSWER:\n"
        f"{answer}\n\n"
        "Return JSON with exactly these keys:\n"
        '{ "summary": "...", "key_insight": "...", "risk_level": "...", "recommendation": "..." }'
    )

    text = llm.invoke(prompt).content
    payload = _extract_json_object(str(text)) or {}

    result: AnalysisResult = _default_result()
    result["summary"] = str(payload.get("summary", "")).strip()
    result["key_insight"] = str(payload.get("key_insight", "")).strip()
    result["risk_level"] = _coerce_risk_level(payload.get("risk_level", "Low"))
    result["recommendation"] = str(payload.get("recommendation", "")).strip()
    return result

