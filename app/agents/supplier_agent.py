from app.agents._common import AgentOutput, analyze_agent_response, analyze_agent_response_async


SUPPLIER_FOCUS = (
    "supplier reliability, vendor concentration, sourcing exposure, contract risk, "
    "quality failures, and supplier-side disruption indicators"
)


def analyze_supplier(rag_answer: str) -> AgentOutput:
    return analyze_agent_response(
        rag_answer=rag_answer,
        agent_name="Supplier Agent",
        focus=SUPPLIER_FOCUS,
    )


async def analyze_supplier_async(rag_answer: str) -> AgentOutput:
    return await analyze_agent_response_async(
        rag_answer=rag_answer,
        agent_name="Supplier Agent",
        focus=SUPPLIER_FOCUS,
    )
