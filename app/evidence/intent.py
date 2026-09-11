"""Lightweight question-intent analysis. Not an agent and not a generator."""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings, openrouter_headers
from app.evidence.parse import extract_json_object
from app.evidence.types import IntentResult
from app.logging_utils import get_logger

logger = get_logger(__name__)

_AMBIGUOUS_PATTERNS = (
    re.compile(r"^\s*what about (?:the )?(.+?)\s*\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*how about (?:the )?(.+?)\s*\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*and (?:the )?(.+?)\s*\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:tell me more|what do you think|any thoughts)\s*\??\s*$", re.IGNORECASE),
)

_INTENT_SYSTEM = """You classify whether a user question is specific enough to answer from documents.
Return JSON only:
{"needs_clarification": true|false, "clarification_question": string|null, "slots": [string]}
needs_clarification is true only when the question is too vague to know what to look up
(for example "what about the supplier?" with no attribute).
If conversation history already resolves the reference, needs_clarification is false.
Do not answer the user's question.
"""


def _clarification_for_slot(slot: str) -> str:
    cleaned = " ".join(slot.split()).strip(" ?.")
    lowered = cleaned.lower()
    if "supplier" in lowered:
        return "Which supplier would you like me to analyze?"
    if cleaned:
        return f"Which {cleaned} would you like me to analyze?"
    return "Could you clarify what you would like to know?"


def heuristic_intent(question: str) -> IntentResult | None:
    text = (question or "").strip()
    if not text:
        return IntentResult(
            needs_clarification=True,
            clarification_question="What would you like to know from your documents?",
            slots=[],
        )
    for pattern in _AMBIGUOUS_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        slot = (match.group(1) if match.lastindex else "") or ""
        slots = [slot.strip()] if slot.strip() else []
        return IntentResult(
            needs_clarification=True,
            clarification_question=_clarification_for_slot(slot),
            slots=slots,
        )
    return None


def _llm_intent(question: str, history: list[dict[str, str]]) -> IntentResult | None:
    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.qa_model,
        temperature=0,
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base,
        default_headers=openrouter_headers(),
        timeout=min(settings.llm_timeout_seconds, 20.0),
        max_retries=0,
    )
    history_lines = []
    for item in history[-8:]:
        role = item.get("role") or "user"
        content = " ".join(str(item.get("content") or "").split())
        if content:
            history_lines.append(f"{role}: {content}")
    user = (
        f"Conversation:\n{chr(10).join(history_lines) or '(none)'}\n\n"
        f"Question:\n{question.strip()}"
    )
    response = llm.invoke(
        [SystemMessage(content=_INTENT_SYSTEM), HumanMessage(content=user)]
    )
    parsed = extract_json_object(str(getattr(response, "content", "") or ""))
    if not parsed:
        return None
    needs = bool(parsed.get("needs_clarification"))
    clarification = parsed.get("clarification_question")
    clarification_text = str(clarification).strip() if clarification else None
    slots_raw = parsed.get("slots") or []
    slots = [str(item).strip() for item in slots_raw if str(item).strip()]
    if needs and not clarification_text:
        clarification_text = _clarification_for_slot(slots[0] if slots else "")
    return IntentResult(
        needs_clarification=needs,
        clarification_question=clarification_text,
        slots=slots,
    )


def analyze_intent(question: str, history: list[dict[str, str]] | None = None) -> IntentResult:
    """Return whether the question is specific enough to retrieve and verify."""
    history = history or []
    heuristic = heuristic_intent(question)
    if heuristic and heuristic.needs_clarification and not history:
        return heuristic
    try:
        llm_result = _llm_intent(question, history)
        if llm_result is not None:
            return llm_result
    except Exception:
        logger.exception("Intent analysis failed; using heuristic")
    if heuristic is not None:
        return heuristic
    return IntentResult(needs_clarification=False, clarification_question=None, slots=[])
