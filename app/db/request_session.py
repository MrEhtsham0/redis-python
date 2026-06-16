from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_custom_logger

logger = get_custom_logger("database.request_session")

DB_ROLLBACK_FLAG = "db_rollback"
DB_SESSION_ATTR = "db"


async def rollback_request_session(request: Request) -> None:
    """
    Roll back the request session and prevent ``get_db`` from committing afterward.

    FastAPI ``AppException`` handlers return JSON without re-raising, so ``get_db``'s
    post-yield ``commit()`` would otherwise persist flushed rows.
    """
    if getattr(request.state, DB_ROLLBACK_FLAG, False):
        return
    session: AsyncSession | None = getattr(request.state, DB_SESSION_ATTR, None)
    if session is None:
        return
    await session.rollback()
    setattr(request.state, DB_ROLLBACK_FLAG, True)
    logger.info("Request DB session rolled back (exception handler)")


