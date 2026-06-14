from langchain_core.messages import AIMessage, SystemMessage

from app.agents.prompts_loader import load_prompt_with_thinking
from app.agents.schemas.code_writer import (
    format_code_writer_output,
    parse_code_writer_response,
)
from app.agents.state import AgentState
from app.agents.streaming import stream_llm_tagged_thinking, stream_text
from app.core import get_custom_logger

logger = get_custom_logger(__name__)

CODE_WRITER_PROMPT = load_prompt_with_thinking("code_writer_prompt.md")


async def code_writer_node(state: AgentState) -> dict:
    logger.info("Code writer agent running.")

    messages = [SystemMessage(content=CODE_WRITER_PROMPT), *state["messages"]]
    _, raw_response = await stream_llm_tagged_thinking(messages)
    result = parse_code_writer_response(raw_response)

    if not result.code.strip():
        raise RuntimeError("Code writer returned empty code")

    formatted = format_code_writer_output(result)
    stream_text(formatted)

    logger.info("Code writer response completed.")
    return {
        "messages": [
            AIMessage(
                content=formatted,
                additional_kwargs={"structured": result.model_dump()},
            )
        ]
    }
