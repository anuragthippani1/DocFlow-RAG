import asyncio
import json
import re
from typing import Any, Literal, TypedDict, cast

from langchain_openai import ChatOpenAI

from app.config import get_settings, openrouter_headers
from app.logging_utils import get_logger

RiskLevel = Literal["Low", "Medium", "High"]
logger = get_logger(__name__)


class AgentOutput(TypedDict):
    risk_level: RiskLevel
    reason: str
    recommended_action: str


class DecisionOutput(TypedDict):
    final_risk: RiskLevel
    final_decision: str
    priority_action: str


def build_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.agent_model,
        temperature=0,
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base,
        default_headers=openrouter_headers(),
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
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


def malformed_agent_output(agent_name: str) -> AgentOutput:
    return default_agent_output(
        f"{agent_name} returned malformed JSON, so DocFlow used a safe fallback."
    )


def default_decision_output() -> DecisionOutput:
    return {
        "final_risk": "Low",
        "final_decision": "No major risk is evident from the available document answer.",
        "priority_action": "Continue monitoring and validate with updated operational data.",
    }


def _agent_prompt(
    rag_answer: str,
    agent_name: str,
    focus: str,
    external_context: dict[str, Any] | None = None,
) -> str:
    context_block = ""
    if external_context:
        context_block = (
            "\nOPTIONAL_EXTERNAL_CONTEXT:\n"
            f"{json.dumps(external_context, indent=2, ensure_ascii=True)}\n"
        )

    return (
        f"You are the {agent_name} in DocFlow/SentriX, a supply-chain intelligence system.\n"
        f"Focus only on this domain: {focus}\n\n"
        "Use ONLY the RAG answer and optional external context below. Do not invent facts.\n"
        "If evidence is weak or absent, say so in the reason and keep risk_level Low.\n"
        "Return ONLY one valid JSON object. No markdown. No code fences. No prose.\n"
        "Required keys: risk_level, reason, recommended_action.\n"
        'risk_level must be exactly one of: "Low", "Medium", "High".\n'
        "reason must cite the evidence signal or say evidence is insufficient.\n"
        "recommended_action must be actionable and concise.\n\n"
        "RAG_ANSWER:\n"
        f"{rag_answer}\n"
        f"{context_block}\n"
        "STRICT_JSON_SCHEMA:\n"
        '{ "risk_level": "Low", "reason": "...", "recommended_action": "..." }'
    )


def _decision_prompt(agent_outputs: list[dict[str, Any]]) -> str:
    return (
        "You are the final Decision Agent in DocFlow/SentriX.\n"
        "Combine domain agent outputs into one business recommendation.\n"
        "Do not add facts that are not present in the agent outputs.\n"
        "Return ONLY one valid JSON object. No markdown. No code fences. No prose.\n"
        "Required keys: final_risk, final_decision, priority_action.\n"
        'final_risk must be exactly one of: "Low", "Medium", "High".\n'
        "Choose final_risk based on the highest material risk across the agents.\n\n"
        "AGENT_OUTPUTS:\n"
        f"{json.dumps(agent_outputs, indent=2, ensure_ascii=True)}\n\n"
        "STRICT_JSON_SCHEMA:\n"
        '{ "final_risk": "Low", "final_decision": "...", "priority_action": "..." }'
    )


def _agent_output_from_payload(payload: dict[str, Any], agent_name: str) -> AgentOutput:
    return {
        "risk_level": coerce_risk_level(payload.get("risk_level", "Low")),
        "reason": str(payload.get("reason", "")).strip()
        or f"{agent_name} did not provide a detailed reason.",
        "recommended_action": str(payload.get("recommended_action", "")).strip()
        or "Review the source documents and validate the finding with operational data.",
    }


async def analyze_agent_response_async(
    rag_answer: str,
    agent_name: str,
    focus: str,
    external_context: dict[str, Any] | None = None,
) -> AgentOutput:
    answer = (rag_answer or "").strip()
    if not answer:
        return default_agent_output("No RAG answer was available for analysis.")

    prompt = _agent_prompt(answer, agent_name, focus, external_context)
    try:
        response = await asyncio.wait_for(
            build_llm().ainvoke(prompt), timeout=get_settings().agent_timeout_seconds
        )
        payload = extract_json_object(str(response.content))
        if not payload:
            logger.warning("Malformed JSON from %s: %s", agent_name, response.content)
            return malformed_agent_output(agent_name)
        return _agent_output_from_payload(payload, agent_name)
    except asyncio.TimeoutError:
        logger.warning("%s timed out", agent_name)
        return default_agent_output(f"{agent_name} timed out while analyzing the answer.")
    except Exception as e:
        logger.exception("%s failed", agent_name)
        return default_agent_output(f"{agent_name} failed to analyze the answer: {e}")


def analyze_agent_response(
    rag_answer: str,
    agent_name: str,
    focus: str,
    external_context: dict[str, Any] | None = None,
) -> AgentOutput:
    answer = (rag_answer or "").strip()
    if not answer:
        return default_agent_output("No RAG answer was available for analysis.")

    try:
        response = build_llm().invoke(_agent_prompt(answer, agent_name, focus, external_context))
        payload = extract_json_object(str(response.content))
        if not payload:
            return malformed_agent_output(agent_name)
        return _agent_output_from_payload(payload, agent_name)
    except Exception as e:
        logger.exception("%s failed", agent_name)
        return default_agent_output(f"{agent_name} failed to analyze the answer: {e}")


def _decision_output_from_payload(payload: dict[str, Any]) -> DecisionOutput:
    fallback = default_decision_output()
    return {
        "final_risk": coerce_risk_level(payload.get("final_risk", "Low")),
        "final_decision": str(payload.get("final_decision", "")).strip()
        or fallback["final_decision"],
        "priority_action": str(payload.get("priority_action", "")).strip()
        or fallback["priority_action"],
    }


async def generate_decision_response_async(
    agent_outputs: list[dict[str, Any]]
) -> DecisionOutput:
    if not agent_outputs:
        return default_decision_output()

    try:
        response = await asyncio.wait_for(
            build_llm().ainvoke(_decision_prompt(agent_outputs)),
            timeout=get_settings().agent_timeout_seconds,
        )
        payload = extract_json_object(str(response.content))
        if not payload:
            logger.warning("Malformed JSON from Decision Agent: %s", response.content)
            return default_decision_output()
        return _decision_output_from_payload(payload)
    except asyncio.TimeoutError:
        logger.warning("Decision Agent timed out")
        return default_decision_output()
    except Exception:
        logger.exception("Decision Agent failed")
        return default_decision_output()


def generate_decision_response(agent_outputs: list[dict[str, Any]]) -> DecisionOutput:
    if not agent_outputs:
        return default_decision_output()

    try:
        response = build_llm().invoke(_decision_prompt(agent_outputs))
        payload = extract_json_object(str(response.content))
        if not payload:
            return default_decision_output()
        return _decision_output_from_payload(payload)
    except Exception:
        logger.exception("Decision Agent failed")
        return default_decision_output()
