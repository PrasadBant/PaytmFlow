import os
import sys
import warnings
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from db_safety import assert_safe_for_destructive_db_setup, resolve_test_database_url
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

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


async def _ensure_database_exists(url: str) -> None:
    """Auto-provisions the dedicated test database on first use, via a
    maintenance connection to the server's own `postgres` database. Only
    ever called with a URL `assert_safe_for_destructive_db_setup` has
    already proven safe (see db_safety.py) - this makes "a dedicated test
    database by default" require zero manual setup (no `createdb` step) on
    a fresh checkout or a fresh CI runner. Never touches the real target
    database's contents: it only ever creates a new, empty database if one
    by that name does not already exist."""
    parsed = make_url(url)
    db_name = parsed.database
    # `str(...)`/`URL.__str__` redacts the password as "***" - this is a
    # real connection, not a log line, so it must use the un-redacted form.
    maintenance_url = parsed.set(database="postgres").render_as_string(hide_password=False)
    maintenance_engine = create_async_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    try:
        async with maintenance_engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": db_name}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        await maintenance_engine.dispose()


@pytest.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Provide async database engine.

    Connects to a DEDICATED test PostgreSQL database - see db_safety.py:
    `TEST_DATABASE_URL` if explicitly set, otherwise `settings.DATABASE_URL`
    with `_test` appended to the database name (auto-created here if it
    does not exist yet). Falls back to SQLite in-memory ONLY when that
    database is unreachable and REQUIRE_POSTGRES is not set, and always
    prints a loud warning when it does. Set REQUIRE_POSTGRES=1 to fail hard
    instead (see `make test-integration-pg`).

    `assert_safe_for_destructive_db_setup` is a hard, fail-closed gate run
    unconditionally, before even attempting a connection or auto-creating
    the database - it is pure URL parsing (no I/O), so there is no reason
    to defer it, and running it first means an unsafe URL is rejected
    before this fixture does ANYTHING to the server, not just before the
    final `drop_all`. This is the last line of defense against ever
    running destructive setup against the real demo/dev database,
    regardless of how `pg_url` was resolved.
    """
    pg_url = resolve_test_database_url(settings.DATABASE_URL)
    assert_safe_for_destructive_db_setup(pg_url)

    use_postgres = False
    connect_exc: Exception | None = None
    try:
        test_engine = create_async_engine(pg_url, echo=False)
        async with test_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        use_postgres = True
    except Exception as exc:
        connect_exc = exc
        # The dedicated test database most likely just doesn't exist yet
        # (first run on this server) - try to provision it and retry once
        # before falling back, so a fresh checkout needs no manual step.
        try:
            await _ensure_database_exists(pg_url)
            test_engine = create_async_engine(pg_url, echo=False)
            async with test_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            use_postgres = True
            connect_exc = None
        except Exception as create_exc:
            connect_exc = create_exc

    if not use_postgres:
        if REQUIRE_POSTGRES:
            pytest.fail(
                f"REQUIRE_POSTGRES=1 but the dedicated test database at "
                f"{pg_url!r} is unavailable and could not be auto-created: "
                f"{connect_exc}. Start it with `docker compose up -d postgres` "
                "before running this target.",
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
        test_engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )

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
