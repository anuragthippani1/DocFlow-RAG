"""OpenRouter implementation of the evidence Verifier contract.

This module never generates a user-facing answer.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings, openrouter_headers
from app.evidence.answerability import (
    apply_safety_rules,
    coerce_condition,
    coerce_relevance,
    coerce_stance,
    fail_closed_verdict,
    relabel_pack,
)
from app.evidence.parse import extract_json_object
from app.evidence.types import EvidencePack, EvidenceVerdict, Relevance, Stance
from app.evidence.verifier import Verifier
from app.logging_utils import get_logger

logger = get_logger(__name__)

_VERIFY_SYSTEM = """You are an evidence verifier, not an answer generator.
Decide whether the numbered excerpts actually support answering the question.
Do not invent facts that are not in the excerpts.
Do not write an answer to the user.

Return JSON only:
{
  "condition": "supported_evidence" | "no_relevant_evidence" | "insufficient_evidence",
  "reason": "short explanation",
  "missing_information": ["..."],
  "items": [{"id": "e1", "relevance": "relevant|not_relevant|uncertain", "stance": "supports|unused|unknown"}]
}

Rules:
- supported_evidence: at least one excerpt contains the information needed to answer.
- no_relevant_evidence: excerpts are unrelated to the question.
- insufficient_evidence: excerpts mention the topic but do not actually answer it, or you are uncertain.
- Never choose supported_evidence when you are uncertain.
- stance "supports" only if that excerpt contains information that answers the question.
"""


class OpenRouterVerifier:
    """Verifier backed by the existing OpenRouter QA model."""

    def verify(self, question: str, evidence_pack: EvidencePack) -> EvidenceVerdict:
        pack, verdict = self.verify_with_pack(question, evidence_pack)
        return verdict

    def verify_with_pack(
        self, question: str, evidence_pack: EvidencePack
    ) -> tuple[EvidencePack, EvidenceVerdict]:
        if not evidence_pack.items:
            verdict = apply_safety_rules(
                evidence_pack,
                condition="no_relevant_evidence",
                reason="No excerpts were retrieved.",
            )
            return evidence_pack, verdict
        try:
            parsed = self._invoke(question, evidence_pack)
        except Exception:
            logger.exception("Evidence verifier failed; failing closed")
            return evidence_pack, fail_closed_verdict(evidence_pack)
        if parsed is None:
            return evidence_pack, fail_closed_verdict(evidence_pack)
        labels: dict[str, tuple[Relevance, Stance]] = {}
        for row in parsed.get("items") or []:
            if not isinstance(row, dict):
                continue
            item_id = str(row.get("id") or "").strip()
            if not item_id:
                continue
            labels[item_id] = (
                coerce_relevance(row.get("relevance")),
                coerce_stance(row.get("stance")),
            )
        labeled = relabel_pack(evidence_pack, labels)
        condition = coerce_condition(parsed.get("condition"))
        reason = str(parsed.get("reason") or "").strip()
        missing_raw = parsed.get("missing_information") or []
        missing = [str(item).strip() for item in missing_raw if str(item).strip()]
        verdict = apply_safety_rules(
            labeled,
            condition=condition,
            reason=reason,
            missing_information=missing,
        )
        return labeled, verdict

    def _invoke(self, question: str, pack: EvidencePack) -> dict | None:
        settings = get_settings()
        llm = ChatOpenAI(
            model=settings.qa_model,
            temperature=0,
            api_key=settings.openai_api_key,
            base_url=settings.openai_api_base,
            default_headers=openrouter_headers(),
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
        excerpts = []
        for item in pack.items:
            page = f", page {item.page}" if item.page is not None else ""
            body = item.excerpt_full or item.excerpt
            excerpts.append(f"[{item.id}] n={item.n} {item.document}{page}\n{body}")
        user = (
            f"Question:\n{question.strip()}\n\n"
            f"Excerpts:\n{chr(10).join(excerpts) if excerpts else '(none)'}"
        )
        response = llm.invoke(
            [SystemMessage(content=_VERIFY_SYSTEM), HumanMessage(content=user)]
        )
        return extract_json_object(str(getattr(response, "content", "") or ""))


def get_verifier() -> Verifier:
    return OpenRouterVerifier()
