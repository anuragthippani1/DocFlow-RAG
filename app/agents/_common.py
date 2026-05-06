import json
import os
import re
from typing import Any, Literal, TypedDict, cast

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


load_dotenv()

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
RiskLevel = Literal["Low", "Medium", "High"]


class AgentOutput(TypedDict):
    risk_level: RiskLevel
    reason: str
    recommended_action: str


class DecisionOutput(TypedDict):
    final_risk: RiskLevel
    final_decision: str
    priority_action: str


def openrouter_headers() -> dict[str, str]:
    return {
        "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", ""),
        "X-Title": os.getenv("OPENROUTER_APP_NAME", "DocFlow-RAG"),
    }


def openai_compatible_base_url() -> str:
    return os.getenv("OPENAI_API_BASE", DEFAULT_OPENROUTER_BASE_URL)


def build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("AGENT_MODEL", "gpt-3.5-turbo"),
        temperature=0,
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=openai_compatible_base_url(),
        default_headers=openrouter_headers(),
    )


def coerce_risk_level(value: Any) -> RiskLevel:
    v = str(value).strip().lower()
    if v == "high":
        return "High"
    if v == "medium":
        return "Medium"
    return "Low"


def extract_json_object(text: str) -> dict[str, Any] | None:
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


def default_agent_output(reason: str = "No risk signal identified.") -> AgentOutput:
    return {
        "risk_level": "Low",
        "reason": reason,
        "recommended_action": "Monitor the document findings and update analysis as new information appears.",
    }


def default_decision_output() -> DecisionOutput:
    return {
        "final_risk": "Low",
        "final_decision": "No major risk is evident from the available document answer.",
        "priority_action": "Continue monitoring and validate with updated operational data.",
    }


def analyze_agent_response(rag_answer: str, agent_name: str, focus: str) -> AgentOutput:
    answer = (rag_answer or "").strip()
    if not answer:
        return default_agent_output("No RAG answer was available for analysis.")

    prompt = (
        f"You are the {agent_name} in a supply-chain intelligence system.\n"
        f"Focus area: {focus}\n\n"
        "Analyze the RAG answer for supply-chain decision risk.\n"
        "Return ONLY a strict JSON object. No markdown. No extra text.\n"
        'risk_level must be exactly one of: "Low", "Medium", "High".\n'
        "Keep the reason and recommended_action concise and actionable.\n\n"
        "RAG_ANSWER:\n"
        f"{answer}\n\n"
        "JSON schema:\n"
        '{ "risk_level": "Low | Medium | High", "reason": "...", "recommended_action": "..." }'
    )

    response = build_llm().invoke(prompt)
    payload = extract_json_object(str(response.content)) or {}

    return {
        "risk_level": coerce_risk_level(payload.get("risk_level", "Low")),
        "reason": str(payload.get("reason", "")).strip()
        or "The agent did not provide a detailed reason.",
        "recommended_action": str(payload.get("recommended_action", "")).strip()
        or "Review the source documents and validate the finding with operational data.",
    }


def generate_decision_response(agent_outputs: list[dict[str, Any]]) -> DecisionOutput:
    if not agent_outputs:
        return default_decision_output()

    prompt = (
        "You are the final decision agent for a supply-chain intelligence system.\n"
        "Combine the domain agent outputs into one business recommendation.\n"
        "Return ONLY a strict JSON object. No markdown. No extra text.\n"
        'final_risk must be exactly one of: "Low", "Medium", "High".\n'
        "The final risk should reflect the highest material concern across agents.\n\n"
        "AGENT_OUTPUTS:\n"
        f"{json.dumps(agent_outputs, indent=2)}\n\n"
        "JSON schema:\n"
        '{ "final_risk": "Low | Medium | High", "final_decision": "...", "priority_action": "..." }'
    )

    response = build_llm().invoke(prompt)
    payload = extract_json_object(str(response.content)) or {}

    return {
        "final_risk": coerce_risk_level(payload.get("final_risk", "Low")),
        "final_decision": str(payload.get("final_decision", "")).strip()
        or default_decision_output()["final_decision"],
        "priority_action": str(payload.get("priority_action", "")).strip()
        or default_decision_output()["priority_action"],
    }
