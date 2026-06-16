"""Stream Tavily Research SSE chunks to the chat UI."""

import json
from collections.abc import AsyncIterator

from langchain_tavily import TavilyResearch

from app.agents.streaming import (
    clear_thinking,
    start_thinking_step,
    stream_event,
    stream_thinking_char,
)
from app.core import get_custom_logger

logger = get_custom_logger("tavily_research_streaming")


class _TavilyResearchStreamParser:
    def __init__(self) -> None:
        self._buffer = ""
        self._answer_started = False
        self.content_parts: list[str] = []

    def feed(self, chunk: bytes) -> None:
        self._buffer += chunk.decode("utf-8", errors="replace")
        while "\n\n" in self._buffer:
            block, self._buffer = self._buffer.split("\n\n", 1)
            self._process_block(block)

    def flush(self) -> None:
        if self._buffer.strip():
            self._process_block(self._buffer)
            self._buffer = ""

    def _process_block(self, block: str) -> None:
        data_line = next((line[5:].strip() for line in block.split("\n") if line.startswith("data:")), None)
        if not data_line:
            return

        try:
            payload = json.loads(data_line)
        except json.JSONDecodeError:
            logger.debug("Skipping non-JSON Tavily SSE block")
            return

        choices = payload.get("choices") or []
        if not choices:
            return

        delta = choices[0].get("delta") or {}
        tool_calls = delta.get("tool_calls")
        if tool_calls:
            self._stream_tool_calls(tool_calls)

        content = delta.get("content")
        if content:
            self._stream_content(content)

    def _stream_tool_calls(self, tool_calls: dict) -> None:
        event_type = tool_calls.get("type")

        if event_type == "tool_call":
            for tool in tool_calls.get("tool_call") or []:
                name = tool.get("name", "tool")
                args = tool.get("arguments", "")
                self._stream_thinking_line(f"\n• **{name}**: {args}\n")
                queries = tool.get("queries")
                if queries:
                    for query in queries:
                        self._stream_thinking_line(f"  - {query}\n")

        elif event_type == "tool_response":
            for tool in tool_calls.get("tool_response") or []:
                name = tool.get("name", "tool")
                args = tool.get("arguments", "")
                self._stream_thinking_line(f"\n✓ **{name}**: {args}\n")
                sources = tool.get("sources") or []
                if sources:
                    self._stream_thinking_line(f"  ({len(sources)} sources found)\n")

    def _stream_thinking_line(self, text: str) -> None:
        for char in text:
            stream_thinking_char(char)

    def _stream_content(self, content: str) -> None:
        if not self._answer_started:
            clear_thinking()
            self._answer_started = True

        self.content_parts.append(content)
        for char in content:
            stream_event("char", char)


async def stream_tavily_research(
    *,
    research_input: str,
    tavily_api_key: str,
    model: str = "mini",
) -> str:
    """
    Run Tavily Research with stream=True and forward progress to the UI.

    Returns the assembled research report markdown.
    """
    start_thinking_step()
    stream_thinking_char("\nStarting Tavily research…\n")

    tool = TavilyResearch(
        tavily_api_key=tavily_api_key,
        model=model,  # type: ignore[arg-type]
    )
    stream = await tool.ainvoke({"input": research_input, "stream": True})

    if not hasattr(stream, "__aiter__"):
        raise RuntimeError("Tavily Research did not return a streaming response")

    parser = _TavilyResearchStreamParser()
    async for chunk in _as_byte_stream(stream):
        parser.feed(chunk)

    parser.flush()
    answer = "".join(parser.content_parts).strip()
    if not answer:
        raise RuntimeError("Tavily Research returned an empty report")

    return answer


async def _as_byte_stream(stream: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    async for chunk in stream:
        if chunk:
            yield chunk
