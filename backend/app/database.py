"""
Async SQLite database connection and session management.

Provides engine, session factory, declarative Base class, and a FastAPI
dependency that yields per-request database sessions with automatic cleanup.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)


# ── Declarative Base ───────────────────────────────────────────────────────


class Base(DeclarativeBase):
    """Declarative base class for all SQLAlchemy ORM models."""


# ── Engine ──────────────────────────────────────────────────────────────────


def create_db_engine(database_url: str, *, echo: bool = False):
    """Create an async SQLAlchemy engine for the given database URL.

    Args:
        database_url: SQLAlchemy async connection URL (e.g. sqlite+aiosqlite:///...).
        echo: Whether to log all SQL statements (debug mode).

    Returns:
        An async SQLAlchemy engine configured for the target database.
    """
    connect_args: dict = {}
    if "sqlite" in database_url:
        # SQLite requires this flag to allow cross-thread access from async pools.
        connect_args["check_same_thread"] = False

    return create_async_engine(
        database_url,
        echo=echo,
        connect_args=connect_args,
    )


# Module-level engine — created once at import time.
engine = create_db_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
)


# ── Session Factory ─────────────────────────────────────────────────────────


def session_factory(bind=None):
    """Create an async session factory bound to an engine.

    Args:
        bind: An async SQLAlchemy engine. Defaults to the module-level engine.

    Returns:
        An async_sessionmaker configured for the given engine.
    """
    _bind = bind or engine
    return async_sessionmaker(
        _bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# Module-level session factory.
AsyncSessionFactory = session_factory()


# ── FastAPI Dependency ─────────────────────────────────────────────────────


async def get_db() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency that yields an async database session.

    Creates a new session per request and closes it after the request
    completes, even if an exception occurs.

    Usage:
        @app.get("/products")
        async def list_products(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Product))
            return result.scalars().all()
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
        finally:
            await session.close()


# ── Database Initialization ─────────────────────────────────────────────────


async def init_db(*, eng=None) -> None:
    """Create all database tables if they do not already exist.

    Should be called during application startup (lifespan handler).
    Also ensures the parent directory for the SQLite database file exists.

    Args:
        eng: Optional engine override for testing. Defaults to module-level engine.
    """
    _eng = eng or engine

    # Ensure the data directory exists for the SQLite database file.
    db_dir = settings.database_path.parent
    db_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Ensured database directory exists: %s", db_dir.resolve())

    async with _eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database tables initialized at %s", settings.database_path)
