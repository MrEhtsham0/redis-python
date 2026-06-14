from langgraph.graph import add_messages
from typing import TypedDict,Annotated


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    next_agent: str
