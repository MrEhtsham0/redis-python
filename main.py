import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from settings import config
from redis_connection import redis_connection
from redis_worker import recover_stuck_jobs, run_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
)

logger = logging.getLogger(__name__)
# Request/Response models
class KeyValueRequest(BaseModel):
    key: str
    value: str

class MessageResponse(BaseModel):
    message: str
    key: str
    value: str

class JobRequest(BaseModel):
    key: str
    value: str


class JobQueuedResponse(BaseModel):
    message: str
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    key: str | None = None
    value: str | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        await redis_connection.ping()
        logger.info("✅ Redis connected successfully")
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        raise

    worker_tasks = []
    client = redis_connection.get_client()
    await recover_stuck_jobs(client)
    for worker_id in range(1, config.worker_count + 1):
        worker_tasks.append(
            asyncio.create_task(run_worker(worker_id=worker_id, manage_connection=False))
        )
    logger.info(f"✅ Started {config.worker_count} job worker(s)")

    yield

    # Shutdown
    for task in worker_tasks:
        task.cancel()
    await asyncio.gather(*worker_tasks, return_exceptions=True)
    await redis_connection.close()
    logger.info("❌ Redis connection closed")

app = FastAPI(lifespan=lifespan)

@app.post("/set", response_model=MessageResponse)
async def set_key(request: KeyValueRequest):
    """Set a key-value pair in Redis."""
    try:
        client = redis_connection.get_client()
        await client.set(request.key, request.value,ex=60)
        logger.info(f"Key {request.key} set successfully")
        return MessageResponse(
            message="Key set successfully",
            key=request.key,
            value=request.value
        )
    except Exception as e:
        logger.error(f"Redis error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Redis error: {str(e)}")

@app.get("/get/{key}")
async def get_key(key: str):
    """Get value by key from Redis."""
    try:
        client = redis_connection.get_client()
        value = await client.get(key)
        if value is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
        return {"key": key, "value": value}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Redis error: {str(e)}")
    
def _job_key(job_id: str) -> str:
    return f"{config.job_key_prefix}{job_id}"


@app.post("/jobs", response_model=JobQueuedResponse, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_job(request: JobRequest):
    """Queue a job for background processing."""
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "key": request.key,
        "value": request.value,
        "status": "pending",
    }

    try:
        client = redis_connection.get_client()
        await client.set(_job_key(job_id), json.dumps(job), ex=3600)
        await client.lpush(config.job_queue, job_id)
        logger.info(f"Job {job_id} queued for key {request.key}")
        return JobQueuedResponse(
            message="Your job has been queued",
            job_id=job_id,
        )
    except Exception as e:
        logger.error(f"Failed to queue job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Redis error: {e}",
        )


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Check the status of a queued job."""
    try:
        client = redis_connection.get_client()
        raw = await client.get(_job_key(job_id))
        if raw is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        job = json.loads(raw)
        return JobStatusResponse(
            job_id=job["job_id"],
            status=job["status"],
            key=job.get("key"),
            value=job.get("value"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Redis error: {e}",
        )