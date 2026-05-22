from typing import Literal

from app.agents._common import AgentOutput, default_agent_output

Domain = Literal["research", "supply_chain", "general"]

RESEARCH_SOURCE_HINTS = (
    "grail",
    "llm",
    "long-horizon",
    "foundation model",
    "fittext",
    "memetic",
    "arxiv",
    "research",
    "indexing",
    "agent discovery",
    "medical claims",
)

SUPPLY_CHAIN_SOURCE_HINTS = (
    "supplier",
    "inventory",
    "logistics",
    "supply chain",
    "warehouse",
    "procurement",
    "shipment",
    "vendor",
)

RESEARCH_ANSWER_HINTS = (
    "methodology",
    "experiment",
    "dataset",
    "benchmark",
    "paper",
    "model architecture",
    "retrieval-augmented",
    "embedding",
)

SUPPLY_CHAIN_ANSWER_HINTS = (
    "supplier",
    "inventory",
    "logistics",
    "lead time",
    "stockout",
    "procurement",
    "warehouse",
)


def _score_hints(text: str, hints: tuple[str, ...]) -> int:
    lowered = text.lower()
    return sum(1 for hint in hints if hint in lowered)


def detect_domain(sources: list[str], answer: str) -> Domain:
    source_blob = " ".join(sources)
    answer_blob = answer or ""
    combined = f"{source_blob} {answer_blob}"

    research_score = _score_hints(source_blob, RESEARCH_SOURCE_HINTS) * 2 + _score_hints(
        answer_blob, RESEARCH_ANSWER_HINTS
    )
    supply_score = _score_hints(source_blob, SUPPLY_CHAIN_SOURCE_HINTS) * 2 + _score_hints(
        answer_blob, SUPPLY_CHAIN_ANSWER_HINTS
    )

    if research_score >= 2 and research_score > supply_score:
        return "research"
    if supply_score >= 2 and supply_score > research_score:
        return "supply_chain"
    if research_score >= 1 and supply_score == 0:
        return "research"
    return "general"


def agents_for_domain(domain: Domain) -> dict[str, bool]:
    if domain == "research":
        return {
            "supplier": False,
            "inventory": False,
            "logistics": False,
            "external_risk": True,
        }
    return {
        "supplier": True,
        "inventory": True,
        "logistics": True,
        "external_risk": True,
    }


def skipped_agent_output(agent_name: str, domain: Domain) -> AgentOutput:
    return default_agent_output(
        f"{agent_name} skipped: document context classified as {domain} (not supply-chain)."
    )
