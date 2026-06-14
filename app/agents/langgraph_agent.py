from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from app.agents.llm import reset_llm
from app.agents.nodes.global_supervisor_node import global_supervisor_node
from app.agents.nodes.tavily_web_search import web_search_node
from app.agents.state import AgentState
from app.agents.nodes.code_writer_node import code_writer_node
from app.core.settings import config
from app.db.redis_connection import redis_connection
from app.core import get_custom_logger

logger = get_custom_logger("LangGraphAgent Agent")


def thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


_agent = None


def _route_after_supervisor(state: AgentState) -> str:
    return state.get("next_agent", "direct_response")


def _build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", global_supervisor_node)
    graph.add_node("code_writer", code_writer_node)
    graph.add_node("web_search", web_search_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        _route_after_supervisor,
        {
            "code_writer": "code_writer",
            "web_search": "web_search",
            "direct_response": END,
        },
    )
    graph.add_edge("code_writer", END)
    graph.add_edge("web_search", END)
    return graph


async def initialize_agent():
    global _agent
    reset_llm()
    logger.info(f"Using OpenAI model: {config.openai_model}")
    checkpointer = redis_connection.get_langgraph_redis_saver()
    await checkpointer.asetup()

    graph = _build_graph()
    _agent = graph.compile(checkpointer=checkpointer)
    logger.info("LangGraph compiled with supervisor routing and Redis checkpointing.")
    return _agent


def get_agent():
    if _agent is None:
        raise RuntimeError("Chat agent is not initialized. Call initialize_agent() on startup.")
    return _agent


def _message_role(message: BaseMessage) -> str:
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, AIMessage):
        return "assistant"
    return message.type


async def get_checkpoint_id(config: dict) -> str | None:
    agent = get_agent()
    snapshot = await agent.aget_state(config)
    return snapshot.config.get("configurable", {}).get("checkpoint_id")


async def _delete_thread_keys(thread_id: str) -> None:
    client = redis_connection.get_client()
    patterns = [
        f"checkpoint:{thread_id}:*",
        f"checkpoint_write:{thread_id}:*",
        f"write_keys_zset:{thread_id}:*",
    ]
    for pattern in patterns:
        async for key in client.scan_iter(match=pattern):
            await client.delete(key)


async def rollback_thread(config: dict, checkpoint_id: str | None) -> None:
    agent = get_agent()
    thread_id = config["configurable"]["thread_id"]
    checkpointer = redis_connection.get_langgraph_redis_saver()

    try:
        if checkpoint_id is None:
            try:
                await checkpointer.adelete_thread(thread_id)
            except Exception:
                await _delete_thread_keys(thread_id)
            logger.info(f"Rolled back new thread {thread_id}")
            return

        rollback_config = {
            "configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}
        }
        snapshot = await agent.aget_state(rollback_config)
        await agent.aupdate_state(rollback_config, snapshot.values)
        logger.info(f"Rolled back thread {thread_id} to checkpoint {checkpoint_id}")
    except Exception:
        logger.exception(f"Failed to rollback thread {thread_id}")


async def get_thread_messages(thread_id: str) -> list[dict[str, str]]:
    agent = get_agent()
    state = await agent.aget_state(thread_config(thread_id))

    if not state.values:
        return []

    messages = state.values.get("messages", [])
    return [
        {"role": _message_role(message), "content": message.content}
        for message in messages
        if hasattr(message, "content")
    ]
