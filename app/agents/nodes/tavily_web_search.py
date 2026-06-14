from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_tavily import TavilySearch

from app.agents.prompts_loader import load_prompt_with_thinking
from app.agents.schemas.web_search import parse_search_plan
from app.agents.state import AgentState
from app.agents.streaming import stream_llm_tagged_thinking, clear_thinking
from app.core import get_custom_logger
from app.core.settings import config

logger = get_custom_logger(__name__)

WEB_SEARCH_PLAN_PROMPT = load_prompt_with_thinking("web_search_plan_prompt.md")
WEB_SEARCH_PROMPT = load_prompt_with_thinking("web_search_prompt.md")


def _latest_user_query(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return message.content
    raise ValueError("No user message found for web search")


def _format_search_results(results: dict) -> str:
    items = results.get("results", [])
    if not items:
        return "No search results found."

    lines = []
    for index, item in enumerate(items, start=1):
        title = item.get("title", "Untitled")
        url = item.get("url", "")
        content = item.get("content", "")
        lines.append(f"{index}. {title}\nURL: {url}\n{content}")
    return "\n\n".join(lines)


async def web_search_node(state: AgentState) -> dict:
    logger.info("Web search agent running.")

    if not config.tavily_api_key_str:
        raise RuntimeError("TAVILY_API_KEY is not configured")

    user_query = _latest_user_query(state)

    plan_messages = [SystemMessage(content=WEB_SEARCH_PLAN_PROMPT), *state["messages"]]
    _, plan_raw = await stream_llm_tagged_thinking(plan_messages)
    search_plan = parse_search_plan(plan_raw, fallback_query=user_query)
    clear_thinking()

    search_tool = TavilySearch(
        max_results=5,
        tavily_api_key=config.tavily_api_key_str,
    )
    search_results = await search_tool.ainvoke({"query": search_plan.search_query})
    formatted_results = _format_search_results(search_results)

    synthesis_messages = [
        SystemMessage(content=WEB_SEARCH_PROMPT),
        *state["messages"],
        HumanMessage(
            content=(
                f"Web search results for query '{search_plan.search_query}':\n\n"
                f"{formatted_results}"
            )
        ),
    ]

    _, answer = await stream_llm_tagged_thinking(
        synthesis_messages,
        stream_output=True,
    )

    if not answer.strip():
        raise RuntimeError("Web search agent returned an empty response")

    logger.info("Web search response completed.")
    return {"messages": [AIMessage(content=answer)]}
