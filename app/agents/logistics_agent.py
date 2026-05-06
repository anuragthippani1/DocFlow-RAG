from app.agents._common import AgentOutput, analyze_agent_response


def analyze_logistics(rag_answer: str) -> AgentOutput:
    return analyze_agent_response(
        rag_answer=rag_answer,
        agent_name="Logistics Agent",
        focus=(
            "transportation delays, route disruption, fulfillment constraints, lead-time risk, "
            "and distribution bottlenecks"
        ),
    )
