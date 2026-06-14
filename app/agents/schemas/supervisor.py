from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.agents.schemas.parse import parse_llm_json


class SupervisorDecision(BaseModel):
    agent: Literal["code_writer", "web_search", "direct_response"]
    reason: str = Field(description="Short explanation for routing choice")
    needs_clarification: bool = False
    response: str | None = None


def parse_supervisor_response(text: str) -> SupervisorDecision:
    try:
        return parse_llm_json(text, SupervisorDecision)
    except ValidationError:
        return SupervisorDecision(
            agent="direct_response",
            reason="Could not parse routing decision",
            response="I'm not sure how to help with that yet. Could you rephrase?",
        )
