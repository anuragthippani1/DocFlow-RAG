from app.agents._common import AgentOutput, analyze_agent_response


def analyze_supplier(rag_answer: str) -> AgentOutput:
    return analyze_agent_response(
        rag_answer=rag_answer,
        agent_name="Supplier Agent",
        focus=(
            "supplier reliability, vendor dependency, sourcing exposure, contract risk, "
            "and supplier-side disruption indicators"
        ),
    )
