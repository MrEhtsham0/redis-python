from langchain_core.messages import AIMessage, HumanMessage

from app.agents.state import AgentState
from app.agents.tavily_research_streaming import stream_tavily_research
from app.core import get_custom_logger
from app.core.settings import config

logger = get_custom_logger("tavily_web_search")


def _latest_user_query(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return message.content
    raise ValueError("No user message found for web search")


async def web_search_node(state: AgentState) -> dict:
    logger.info("Web search agent running.")

    if not config.tavily_api_key_str:
        raise RuntimeError("TAVILY_API_KEY is not configured")

    user_query = _latest_user_query(state)
    answer = await stream_tavily_research(
        research_input=user_query,
        tavily_api_key=config.tavily_api_key_str,
        model=config.tavily_research_model,
    )

    logger.info("Web search response completed.")
    return {"messages": [AIMessage(content=answer)]}
