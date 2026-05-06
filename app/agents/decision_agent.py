from typing import Any

from app.agents._common import DecisionOutput, generate_decision_response


def generate_final_decision(agent_outputs: list[dict[str, Any]]) -> DecisionOutput:
    return generate_decision_response(agent_outputs)
