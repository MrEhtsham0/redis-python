from fastapi import APIRouter
from app.routes.agent_route import router as agent_router
from app.routes.queue_job_route import router as queue_job_router

router = APIRouter()

router.include_router(agent_router)
router.include_router(queue_job_router)