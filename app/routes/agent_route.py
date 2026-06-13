import json
import uuid
from fastapi import APIRouter,status,HTTPException
from fastapi.responses import StreamingResponse
from app.validations.chatbot_validations import ChatRequest, ChatHistoryResponse, ChatMessage
from app.agents.langgraph_agent import get_agent, get_checkpoint_id, get_thread_messages, thread_config, rollback_thread
from langchain_core.messages import HumanMessage

from app.core import get_custom_logger
logger = get_custom_logger("AgentRoute")

router = APIRouter(prefix="/agent",tags=["Agent"])

def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """Stream chat tokens via Server-Sent Events."""
    thread_id = request.thread_id or str(uuid.uuid4())

    async def event_generator():
        yield _sse_event({"type": "thread_id", "thread_id": thread_id})

        agent = get_agent()
        config = thread_config(thread_id)
        checkpoint_id = await get_checkpoint_id(config)

        try:
            async for chunk in agent.astream(
                {"messages": [HumanMessage(content=request.message)]},
                config=config,
                stream_mode="custom",
            ):
                content = chunk.get("content") if isinstance(chunk, dict) else None
                if content:
                    yield _sse_event({"type": "char", "content": str(content)})
        except Exception as e:
            await rollback_thread(config, checkpoint_id)
            logger.error(f"Chat stream error: {e}")
            yield _sse_event({"type": "rollback"})
            yield _sse_event({"type": "error", "message": str(e)})
            return
        yield _sse_event({"type": "done"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/{thread_id}", response_model=ChatHistoryResponse)
async def get_chat_history(thread_id: str):
    """Get conversation history for a thread."""
    try:
        messages = await get_thread_messages(thread_id)
        return ChatHistoryResponse(
            thread_id=thread_id,
            messages=[ChatMessage(**message) for message in messages],
        )
    except Exception as e:
        logger.error(f"Failed to fetch chat history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat error: {e}",
        )