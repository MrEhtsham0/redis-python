# import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
# from app.core import config
from app.db.redis_connection import redis_connection
from app.agents.langgraph_agent import initialize_agent
# from app.db.redis_worker import recover_stuck_jobs, run_worker
from app.core import get_custom_logger
from app.routes.api import router


logger = get_custom_logger("main.py")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        await redis_connection.ping()
        logger.info("✅ Redis connected successfully")
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        raise

    # worker_tasks = []
    # client = redis_connection.get_client()
    # await recover_stuck_jobs(client)
    # for worker_id in range(1, config.worker_count + 1):
        # worker_tasks.append(
            # asyncio.create_task(run_worker(worker_id=worker_id, manage_connection=False))
        # )
    # logger.info(f"✅ Started {config.worker_count} job worker(s)")
    await initialize_agent()

    yield

    # Shutdown
    # for task in worker_tasks:
        # task.cancel()
    # await asyncio.gather(*worker_tasks, return_exceptions=True)
    await redis_connection.close()
    logger.info("❌ Redis connection closed")

app = FastAPI(lifespan=lifespan)
app.include_router(router)

CHAT_UI_PATH = Path(__file__).parent / "static" / "chat.html"


@app.get("/", response_class=HTMLResponse)
async def chat_ui():
    """Serve the streaming chat UI."""
    return CHAT_UI_PATH.read_text(encoding="utf-8")