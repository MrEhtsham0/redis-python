from langchain_core.messages import AIMessage, SystemMessage

from app.agents.prompts_loader import load_prompt_with_thinking
from app.agents.schemas.supervisor import parse_supervisor_response
from app.agents.state import AgentState
from app.agents.streaming import stream_llm_tagged_thinking, stream_text, clear_thinking
from app.core import get_custom_logger

logger = get_custom_logger(__name__)

SUPERVISOR_PROMPT = load_prompt_with_thinking("global_supervisor_prompt.md")
VALID_AGENTS = {"code_writer", "web_search", "direct_response"}


async def global_supervisor_node(state: AgentState) -> dict:
    logger.info("Supervisor routing user message.")

    messages = [SystemMessage(content=SUPERVISOR_PROMPT), *state["messages"]]
    _, raw_response = await stream_llm_tagged_thinking(messages)
    decision = parse_supervisor_response(raw_response)

    if decision.agent not in VALID_AGENTS:
        decision.agent = "direct_response"
        decision.response = "I'm not sure how to help with that yet. Could you rephrase?"

    logger.info(f"Supervisor routed to {decision.agent}: {decision.reason}")

    if decision.agent == "direct_response":
        reply = decision.response or "How can I help you today?"
        stream_text(reply)
        return {
            "next_agent": "direct_response",
            "messages": [AIMessage(content=reply)],
        }

    clear_thinking()
    return {"next_agent": decision.agent}
