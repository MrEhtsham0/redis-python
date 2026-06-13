from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    thread_id: str
    reply: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatHistoryResponse(BaseModel):
    thread_id: str
    messages: list[ChatMessage]