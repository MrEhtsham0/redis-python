from langchain_core.messages import AIMessage, SystemMessage

from app.agents.prompts_loader import load_prompt_with_thinking
from app.agents.schemas.supervisor import parse_supervisor_response
from app.agents.state import AgentState
from app.agents.streaming import (
    clear_thinking,
    start_thinking_step,
    stream_llm_tagged_thinking,
    stream_text,
    stream_thinking_char,
)
from app.core import get_custom_logger

logger = get_custom_logger("global_supervisor_node")

SUPERVISOR_PROMPT = load_prompt_with_thinking("global_supervisor_prompt.md")
VALID_AGENTS = {"code_writer", "web_search", "postgres_db", "direct_response"}


async def global_supervisor_node(state: AgentState) -> dict:
    logger.info("Supervisor routing user message.")

    messages = [SystemMessage(content=SUPERVISOR_PROMPT), *state["messages"]]

    start_thinking_step()
    thinking, raw_response = await stream_llm_tagged_thinking(
        messages,
        external_thinking_started=True,
    )
    decision = parse_supervisor_response(raw_response)

    if decision.agent not in VALID_AGENTS:
        decision.agent = "direct_response"
        decision.response = "I'm not sure how to help with that yet. Could you rephrase?"

    logger.info(f"Supervisor routed to {decision.agent}: {decision.reason}")

    if not thinking.strip() and decision.reason:
        prefix = "" if not thinking else "\n"
        for char in f"{prefix}{decision.reason}":
            stream_thinking_char(char)

    if decision.agent == "direct_response":
        reply = decision.response or "How can I help you today?"
        stream_text(reply)
        return {
            "next_agent": "direct_response",
            "messages": [AIMessage(content=reply)],
        }

    clear_thinking()
    return {"next_agent": decision.agent}
