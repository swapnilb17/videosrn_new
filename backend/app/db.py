from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings
from app.models import Base


def _engine_connect_args(database_url: str) -> dict:
    if "sqlite" in database_url:
        return {"check_same_thread": False}
    return {}


def normalize_postgres_url_for_async(url: str) -> str:
    """Async engine needs an async driver; plain postgresql:// loads psycopg2 and fails."""
    u = (url or "").strip()
    if not u.startswith("postgresql://"):
        return u
    if u.startswith("postgresql+"):
        return u
    return "postgresql+asyncpg://" + u[len("postgresql://") :]


def create_async_engine_from_settings(settings: Settings) -> AsyncEngine:
    url = normalize_postgres_url_for_async((settings.database_url or "").strip())
    kw: dict = {
        "echo": False,
        "connect_args": _engine_connect_args(url),
    }
    # Topic-to-video and other async jobs can hold one session open for many minutes while
    # FFmpeg / Veo run. Default pool (5 + overflow) starves short reads like /internal/user-media
    # and causes long waits → Next.js aborts with 504.
    if "postgresql" in url:
        kw.update(
            pool_size=25,
            max_overflow=55,
            pool_timeout=120,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
    return create_async_engine(url, **kw)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession | None]:
    factory: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "session_factory", None
    )
    if factory is None:
        yield None
        return
    async with factory() as session:
        yield session


async def ping_database(session: AsyncSession) -> bool:
    from sqlalchemy import text

    await session.execute(text("SELECT 1"))
    return True


async def create_tables_if_needed(engine: AsyncEngine) -> None:
    """For tests (SQLite); production should use Alembic."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
