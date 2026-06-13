import json
import uuid
from fastapi import APIRouter,status,HTTPException
from app.validations.queue_job_validations import KeyValueRequest, MessageResponse, JobRequest, JobQueuedResponse, JobStatusResponse
from app.db.redis_connection import redis_connection
from app.core import config
from app.core import get_custom_logger
logger = get_custom_logger("QueueJobRoute")

router = APIRouter(prefix="/queue",tags=["Queue"])



@router.post("/set", response_model=MessageResponse)
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

@router.get("/get/{key}")
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


@router.post("/jobs", response_model=JobQueuedResponse, status_code=status.HTTP_202_ACCEPTED)
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


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
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