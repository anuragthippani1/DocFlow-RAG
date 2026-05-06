from app.agents._common import AgentOutput, analyze_agent_response


def analyze_inventory(rag_answer: str) -> AgentOutput:
    return analyze_agent_response(
        rag_answer=rag_answer,
        agent_name="Inventory Agent",
        focus=(
            "inventory availability, demand-supply mismatch, stockout exposure, buffer levels, "
            "and replenishment risk"
        ),
    )
