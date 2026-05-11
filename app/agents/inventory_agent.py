from app.agents._common import AgentOutput, analyze_agent_response, analyze_agent_response_async


INVENTORY_FOCUS = (
    "inventory availability, demand-supply mismatch, stockout exposure, excess inventory, "
    "buffer levels, and replenishment risk"
)


def analyze_inventory(rag_answer: str) -> AgentOutput:
    return analyze_agent_response(
        rag_answer=rag_answer,
        agent_name="Inventory Agent",
        focus=INVENTORY_FOCUS,
    )


async def analyze_inventory_async(rag_answer: str) -> AgentOutput:
    return await analyze_agent_response_async(
        rag_answer=rag_answer,
        agent_name="Inventory Agent",
        focus=INVENTORY_FOCUS,
    )
