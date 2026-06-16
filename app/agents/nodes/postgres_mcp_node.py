from langchain_core.messages import AIMessage, SystemMessage
from langchain.agents import create_agent
from app.agents.llm import get_llm
from app.agents.mcp.postgres_mcp import get_postgres_mcp_tools
from app.agents.prompts_loader import load_prompt_with_thinking
from app.agents.state import AgentState
from app.agents.streaming import stream_react_agent_events, stream_text
from app.core import get_custom_logger

logger = get_custom_logger("postgres_mcp_node")

POSTGRES_MCP_PROMPT = load_prompt_with_thinking("postgres_mcp_prompt.md")

_postgres_agent = None


async def _get_postgres_agent():
    global _postgres_agent
    if _postgres_agent is None:
        tools = await get_postgres_mcp_tools()
        _postgres_agent = create_agent(get_llm(), tools)
    return _postgres_agent


async def postgres_mcp_node(state: AgentState) -> dict:
    logger.info("Postgres MCP agent running.")

    try:
        agent = await _get_postgres_agent()
    except Exception as exc:
        logger.exception("Postgres MCP agent unavailable")
        message = f"Database tools are unavailable: {exc}"
        stream_text(message)
        return {"messages": [AIMessage(content=message)]}

    messages = [SystemMessage(content=POSTGRES_MCP_PROMPT), *state["messages"]]
    content = await stream_react_agent_events(agent, {"messages": messages})

    if not content:
        content = "No response from the database agent."

    logger.info("Postgres MCP response completed.")
    return {"messages": [AIMessage(content=content)]}
