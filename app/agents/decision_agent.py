from typing import Any

from app.agents._common import (
    DecisionOutput,
    generate_decision_response,
    generate_decision_response_async,
)


def generate_final_decision(agent_outputs: list[dict[str, Any]]) -> DecisionOutput:
    return generate_decision_response(agent_outputs)


async def generate_final_decision_async(
    agent_outputs: list[dict[str, Any]]
) -> DecisionOutput:
    return await generate_decision_response_async(agent_outputs)
