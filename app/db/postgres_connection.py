"""
Async SQLAlchemy database connection.

Provides:
- engine + async sessionmaker
- `init_db()` — initialise engine/session (schema: use Alembic, not `create_all`)
- `get_db()` FastAPI dependency
- `dispose_db()` for shutdown

DB provisioning (CREATE DATABASE / extensions) lives in ``scripts/bootstrap.sh``.
"""

from typing import Any, AsyncGenerator, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core import config
from app.core import get_custom_logger
from app.db.request_session import DB_ROLLBACK_FLAG, DB_SESSION_ATTR
# from app.exceptions.exception_handler import AuthError

logger = get_custom_logger("database.connection")


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass

_engine: Any = None
_async_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """
    Return the global async sessionmaker.

    Used in places where we need to create additional independent sessions
    (e.g. for concurrent background tasks) instead of reusing a single session.
    """
    if _async_sessionmaker is None:
        raise Exception("Database not initialised; call init_db() at startup.")
    return _async_sessionmaker


async def init_db() -> None:
    """Initialise async engine and sessionmaker. Apply schema with `alembic upgrade head`."""
    global _engine, _async_sessionmaker
    if _engine is not None:
        return

    try:
        database_url = config.postgres_async_url
    except Exception as exc:
        logger.warning(f"Database URL not configured, skipping async DB init: {exc}")
        return

    _engine = create_async_engine(
        database_url,
        pool_size=config.db_pool_size,
        max_overflow=config.db_max_overflow,
        pool_pre_ping=True,
        pool_timeout=config.db_pool_timeout,
    )
    _async_sessionmaker = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    logger.info("Async database engine and session factory initialised")


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an `AsyncSession`.

    One session per request. Successful handlers are committed here; unhandled
    errors roll back. ``AppException`` handlers call ``rollback_request_session``
    so flushed rows are not committed when the handler returns 4xx/5xx JSON.
    """
    if _async_sessionmaker is None:
        logger.error("❌ Database not initialised. Call init_db() at startup.", exc_info=True)
        raise Exception("Database not initialised. Call init_db() at startup.")

    async with _async_sessionmaker() as session:
        setattr(request.state, DB_SESSION_ATTR, session)
        try:
            yield session
            if not getattr(request.state, DB_ROLLBACK_FLAG, False):
                await session.commit()
        except Exception:
            await session.rollback()
            setattr(request.state, DB_ROLLBACK_FLAG, True)
            raise
        finally:
            await session.close()


async def dispose_db() -> None:
    """Dispose the engine (e.g. on app shutdown)."""
    global _engine, _async_sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_sessionmaker = None
        logger.info("Database engine disposed")

async def create_tables() -> None:
    """Create all ORM tables. Models must be imported so they register on Base.metadata."""
    await init_db()
    if _engine is None:
        raise RuntimeError("Database engine not initialised — check Postgres settings in .env")

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    table_names = ", ".join(sorted(Base.metadata.tables.keys())) or "none"
    logger.info(f"Database tables ready: {table_names}")