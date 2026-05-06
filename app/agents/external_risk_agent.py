from app.agents._common import AgentOutput, analyze_agent_response


def analyze_external_risk(rag_answer: str) -> AgentOutput:
    return analyze_agent_response(
        rag_answer=rag_answer,
        agent_name="External Risk Agent",
        focus=(
            "geopolitical, regulatory, market, climate, financial, and macro disruption risks "
            "that could affect supply-chain decisions"
        ),
    )
