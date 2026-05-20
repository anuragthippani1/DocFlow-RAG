from typing import Literal, TypedDict

from app.agents._common import build_llm, coerce_risk_level, extract_json_object


RiskLevel = Literal["Low", "Medium", "High"]


class AnalysisResult(TypedDict):
    summary: str
    key_insight: str
    risk_level: RiskLevel
    recommendation: str


def _default_result() -> AnalysisResult:
    return {
        "summary": "",
        "key_insight": "",
        "risk_level": "Low",
        "recommendation": "",
    }


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

    llm = build_llm()

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
    payload = extract_json_object(str(text)) or {}

    result: AnalysisResult = _default_result()
    result["summary"] = str(payload.get("summary", "")).strip()
    result["key_insight"] = str(payload.get("key_insight", "")).strip()
    result["risk_level"] = coerce_risk_level(payload.get("risk_level", "Low"))
    result["recommendation"] = str(payload.get("recommendation", "")).strip()
    return result

