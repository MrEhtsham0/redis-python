import logging
from typing import Annotated

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph, add_messages
from typing_extensions import TypedDict

from app.db.redis_connection import redis_connection
from app.core.settings import config

logger = logging.getLogger(__name__)


class BasicChatState(TypedDict):
    messages: Annotated[list, add_messages]


_llm: ChatOpenAI | None = None
_agent = None


def _get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            model=config.openai_model,
            api_key=config.openai_api_key_str,
            streaming=True,
        )
    return _llm


def thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _normalize_content(content: str | list) -> str:
    if not content:
        return ""
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content


async def get_checkpoint_id(config: dict) -> str | None:
    agent = get_agent()
    snapshot = await agent.aget_state(config)
    return snapshot.config.get("configurable", {}).get("checkpoint_id")


async def _delete_thread_keys(thread_id: str) -> None:
    """Fallback cleanup when RediSearch index is unavailable."""
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
    """Restore thread to the checkpoint from before the failed turn."""
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


async def chatbot(state: BasicChatState) -> dict:
    logger.info("Streaming LLM response.")
    writer = get_stream_writer()
    full_response = ""

    try:
        async for chunk in _get_llm().astream(state["messages"]):
            token = _normalize_content(chunk.content)
            if not token:
                continue
            full_response += token
            for char in token:
                writer({"content": char})
    except Exception:
        logger.exception("LLM streaming failed")
        raise

    if not full_response.strip():
        raise RuntimeError("LLM returned an empty response")

    logger.info("LLM response received.")
    return {"messages": [AIMessage(content=full_response)]}


def _build_graph() -> StateGraph:
    graph = StateGraph(BasicChatState)
    graph.add_node("chatbot", chatbot)
    graph.add_edge(START, "chatbot")
    graph.add_edge("chatbot", END)
    return graph


async def initialize_agent():
    global _agent
    checkpointer = redis_connection.get_langgraph_redis_saver()
    await checkpointer.asetup()

    graph = _build_graph()
    _agent = graph.compile(checkpointer=checkpointer)
    logger.info("LangGraph compiled with Redis checkpointing.")
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


async def chat(message: str, thread_id: str) -> str:
    agent = get_agent()
    config = thread_config(thread_id)
    checkpoint_id = await get_checkpoint_id(config)

    try:
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            config=config,
        )
        last_message = result["messages"][-1]
        return last_message.content
    except Exception:
        await rollback_thread(config, checkpoint_id)
        raise


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
