from app.agents._common import AgentOutput, analyze_agent_response, analyze_agent_response_async


LOGISTICS_FOCUS = (
    "transportation delays, route disruption, fulfillment constraints, lead-time risk, "
    "port congestion, carrier reliability, and distribution bottlenecks"
)


def analyze_logistics(rag_answer: str) -> AgentOutput:
    return analyze_agent_response(
        rag_answer=rag_answer,
        agent_name="Logistics Agent",
        focus=LOGISTICS_FOCUS,
    )


async def analyze_logistics_async(rag_answer: str) -> AgentOutput:
    return await analyze_agent_response_async(
        rag_answer=rag_answer,
        agent_name="Logistics Agent",
        focus=LOGISTICS_FOCUS,
    )
