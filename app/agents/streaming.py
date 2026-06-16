from langchain_core.messages import BaseMessage
from langgraph.config import get_stream_writer

from app.agents.llm import get_llm, normalize_content


def stream_event(event_type: str, content: str) -> None:
    writer = get_stream_writer()
    writer({"type": event_type, "content": content})


def start_thinking_step() -> None:
    stream_event("thinking_start", "")


def stream_thinking_char(char: str) -> None:
    stream_event("thinking_char", char)


def stream_thinking(text: str) -> None:
    start_thinking_step()
    for char in text:
        stream_thinking_char(char)


def clear_thinking() -> None:
    stream_event("thinking_clear", "")


class _ThinkingStreamParser:
    def __init__(self, *, tag: str = "thinking", stream_output: bool = False) -> None:
        self.open_tag = f"<{tag}>"
        self.close_tag = f"</{tag}>"
        self.stream_output = stream_output
        self.buffer = ""
        self.phase = "before"
        self.thinking = ""
        self.output = ""
        self._thinking_step_open = False

    def push(self, token: str) -> None:
        self.buffer += token

        while True:
            if self.phase == "before":
                open_idx = self.buffer.find(self.open_tag)
                if open_idx == -1:
                    if len(self.buffer) > len(self.open_tag):
                        self.buffer = self.buffer[-len(self.open_tag) :]
                    return

                self.buffer = self.buffer[open_idx + len(self.open_tag) :]
                self.phase = "in"
                if not self._thinking_step_open:
                    start_thinking_step()
                    self._thinking_step_open = True
                continue

            if self.phase == "in":
                close_idx = self.buffer.find(self.close_tag)
                if close_idx == -1:
                    holdback = len(self.close_tag) - 1
                    safe_end = max(0, len(self.buffer) - holdback)
                    chunk = self.buffer[:safe_end]
                    self.buffer = self.buffer[safe_end:]
                    self._append_thinking(chunk)
                    return

                chunk = self.buffer[:close_idx]
                self.buffer = self.buffer[close_idx + len(self.close_tag) :]
                self._append_thinking(chunk)
                self.phase = "after"
                if self.stream_output:
                    clear_thinking()
                continue

            if self.phase == "after":
                if self.buffer:
                    if self.stream_output:
                        for char in self.buffer:
                            stream_event("char", char)
                    self.output += self.buffer
                    self.buffer = ""
                return

    def _append_thinking(self, text: str) -> None:
        if not text:
            return
        self.thinking += text
        for char in text:
            stream_thinking_char(char)

    @property
    def saw_thinking(self) -> bool:
        return self.phase != "before"


async def stream_llm_tagged_thinking(
    messages: list[BaseMessage],
    *,
    tag: str = "thinking",
    stream_output: bool = False,
    external_thinking_started: bool = False,
) -> tuple[str, str]:
    """
    Stream model reasoning from <thinking> tags to the UI.
    Returns (thinking_text, trailing_output_for_parsing or display).
    """
    parser = _ThinkingStreamParser(tag=tag, stream_output=stream_output)
    if external_thinking_started:
        parser._thinking_step_open = True
    full_raw = ""

    async for chunk in get_llm().astream(messages):
        token = normalize_content(chunk.content)
        if not token:
            continue
        full_raw += token
        parser.push(token)

    if parser.phase == "after" and parser.buffer:
        parser.push("")

    if not parser.saw_thinking:
        if stream_output:
            for char in full_raw:
                stream_event("char", char)
        return "", full_raw.strip()

    return parser.thinking.strip(), parser.output.strip()


async def stream_llm_thinking(messages: list[BaseMessage]) -> str:
    _, output = await stream_llm_tagged_thinking(messages)
    return output


async def stream_llm_response(messages: list[BaseMessage]) -> str:
    _, output = await stream_llm_tagged_thinking(messages, stream_output=True)
    return output


def stream_text(text: str) -> None:
    clear_thinking()
    for char in text:
        stream_event("char", char)


async def stream_react_agent_events(agent, input_state: dict) -> str:
    """
    Stream a LangGraph ReAct agent run to the UI.

    Tool calls update the thinking panel live; the final LLM turn streams
    <thinking> tags then answer characters as they are generated.
    """
    from app.agents.llm import normalize_content

    start_thinking_step()
    parser = _ThinkingStreamParser(stream_output=True)
    final_content = ""

    async for event in agent.astream_events(input_state, version="v2"):
        kind = event.get("event")

        if kind == "on_tool_start":
            tool_name = event.get("name", "tool")
            for char in f"\n• `{tool_name}` running…\n":
                stream_thinking_char(char)

        elif kind == "on_chat_model_start":
            parser = _ThinkingStreamParser(stream_output=True)

        elif kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if getattr(chunk, "tool_call_chunks", None):
                continue
            token = normalize_content(chunk.content)
            if token:
                parser.push(token)

        elif kind == "on_chat_model_end":
            output = event["data"]["output"]
            if getattr(output, "tool_calls", None):
                continue

            content = normalize_content(output.content)
            if parser.phase == "after" and parser.buffer:
                parser.push("")

            if parser.saw_thinking:
                final_content = parser.output.strip() or content
            else:
                final_content = content
                if final_content:
                    clear_thinking()
                    for char in final_content:
                        stream_event("char", char)

    return final_content.strip()
