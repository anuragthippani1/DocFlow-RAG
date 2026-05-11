from typing import Any

from app.agents._common import AgentOutput, analyze_agent_response, analyze_agent_response_async


EXTERNAL_RISK_FOCUS = (
    "geopolitical, regulatory, market, climate, financial, weather, news, shipping, "
    "and macro disruption risks that could affect supply-chain decisions"
)


def analyze_external_risk(rag_answer: str) -> AgentOutput:
    return analyze_agent_response(
        rag_answer=rag_answer,
        agent_name="External Risk Agent",
        focus=EXTERNAL_RISK_FOCUS,
    )


async def analyze_external_risk_async(
    rag_answer: str, external_context: dict[str, Any] | None = None
) -> AgentOutput:
    return await analyze_agent_response_async(
        rag_answer=rag_answer,
        agent_name="External Risk Agent",
        focus=EXTERNAL_RISK_FOCUS,
        external_context=external_context,
    )
