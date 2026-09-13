import os
import sys
import warnings
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.db.models import Base
from app.db.session import create_immutability_triggers, get_db
from app.main import app

# The integration suite exercises real relational behaviour (foreign keys, the
# append-only triggers, row locking) that SQLite does not enforce the same way
# PostgreSQL does. A silent SQLite fallback previously masked a real
# ForeignKeyViolation that only ever surfaced against PostgreSQL (B17/B30/B31).
#
# Set REQUIRE_POSTGRES=1 (the `make test-integration-pg` / CI target does this)
# to make an unreachable PostgreSQL a hard failure instead of a silent fallback.
# Without it, a fallback is still permitted for quick local unit-style runs, but
# it is now loud - printed to stderr and raised as a pytest warning - never silent.
REQUIRE_POSTGRES = os.environ.get("REQUIRE_POSTGRES", "").lower() in ("1", "true", "yes")


@pytest.fixture(scope="session")
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Provide async database engine.

    Connects to PostgreSQL. Falls back to SQLite in-memory ONLY when
    REQUIRE_POSTGRES is not set, and always prints a loud warning when it does.
    Set REQUIRE_POSTGRES=1 to fail hard instead (see `make test-integration-pg`).
    """
    pg_url = settings.DATABASE_URL
    if pg_url.startswith("postgresql://"):
        pg_url = pg_url.replace("postgresql://", "postgresql+psycopg://", 1)

    use_postgres = False
    try:
        test_engine = create_async_engine(pg_url, echo=False)
        async with test_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        use_postgres = True
    except Exception as exc:
        if REQUIRE_POSTGRES:
            pytest.fail(
                f"REQUIRE_POSTGRES=1 but PostgreSQL is unavailable at "
                f"{settings.DATABASE_URL!r}: {exc}. Start it with "
                f"`docker compose up -d postgres` before running this target.",
                pytrace=False,
            )
        message = (
            "PostgreSQL unavailable - integration tests are falling back to an "
            "in-memory SQLite engine. SQLite does NOT enforce foreign keys the "
            "way PostgreSQL does; this can hide real defects (see B17/B30). "
            "Run with REQUIRE_POSTGRES=1 (`make test-integration-pg`) against a "
            "real PostgreSQL instance before trusting this run."
        )
        print(f"\n\033[93mWARNING: {message}\033[0m", file=sys.stderr)
        warnings.warn(message, stacklevel=2)
        test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with test_engine.begin() as conn:
        if use_postgres:
            # Recreate schema cleanly for integration testing
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await create_immutability_triggers(conn)

    yield test_engine

    if use_postgres:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest.fixture
async def client(db_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as http_client:
        yield http_client

    app.dependency_overrides.clear()


@pytest.fixture
def session_headers() -> dict[str, str]:
    return {"X-Session-Id": str(uuid4())}


@pytest.fixture
def other_session_headers() -> dict[str, str]:
    return {"X-Session-Id": str(uuid4())}
