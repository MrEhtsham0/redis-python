import asyncio
import json
import logging

from redis.asyncio import Redis
from redis_connection import redis_connection
from settings import config
logger = logging.getLogger(__name__)



def _job_key(job_id: str) -> str:
    return f"{config.job_key_prefix}{job_id}"


async def _fetch_job(client: Redis, job_id: str) -> dict | None:
    raw = await client.get(_job_key(job_id))
    if raw is None:
        return None
    return json.loads(raw)


async def _update_job_status(client: Redis, job_id: str, status: str) -> None:
    job = await _fetch_job(client, job_id)
    if job is None:
        return
    job["status"] = status
    await client.set(_job_key(job_id), json.dumps(job), ex=3600)


async def recover_stuck_jobs(client: Redis) -> None:
    """Move jobs left in processing queue back to main queue after a crash."""
    while True:
        job_id = await client.rpop(config.job_processing_queue)
        if job_id is None:
            break
        await client.lpush(config.job_queue, job_id)
        logger.info(f"Recovered stuck job {job_id} back to {config.job_queue}")


async def process_job(client: Redis, job_id: str) -> None:
    job = await _fetch_job(client, job_id)
    if job is None:
        logger.warning(f"Job {job_id} not found, skipping")
        return

    if job.get("status") != "pending":
        logger.info(f"Job {job_id} already processed (status={job.get('status')})")
        return

    await _update_job_status(client, job_id, "processing")

    try:
        await client.set(job["key"], job["value"], ex=60)
        await _update_job_status(client, job_id, "completed")
        logger.info(f"Job {job_id} completed: set {job['key']}")
    except Exception:
        await _update_job_status(client, job_id, "failed")
        logger.exception(f"Job {job_id} failed")
        raise


async def run_worker(*, worker_id: int = 1, manage_connection: bool = True) -> None:
    """Run a worker to process jobs from the job queue.
    and pass the arguments as keyword arguments.
    Args:
        worker_id: The ID of the worker.
        manage_connection: Whether to manage the connection to the Redis server.
    Returns:
        None
    """
    client = redis_connection.get_client()
    logger.info(
        f"Worker {worker_id} started, waiting for jobs on {config.job_queue} "
        f"(processing list: {config.job_processing_queue})..."
    )

    try:
        while True:
            job_id = await client.brpoplpush(
                config.job_queue, config.job_processing_queue, timeout=config.brpop_timeout
            )
            if job_id is None:
                continue

            try:
                logger.info(f"Worker {worker_id} picked up job {job_id}")
                await process_job(client, job_id)
            finally:
                await client.lrem(config.job_processing_queue, 1, job_id)
    except asyncio.CancelledError:
        logger.info(f"Worker {worker_id} shutting down...")
        raise
    finally:
        if manage_connection:
            await redis_connection.close()
