import sys
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

if sys.platform == "win32":
    import asyncio

    if not isinstance(
        asyncio.get_event_loop_policy(), asyncio.WindowsSelectorEventLoopPolicy
    ):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Format async connection string if necessary
db_url = settings.DATABASE_URL
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

engine: AsyncEngine = create_async_engine(
    db_url,
    echo=False,
    future=True,
)

async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncGenerator[AsyncSession, Any]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_immutability_triggers(conn_or_session) -> None:
    """Create append-only immutability triggers on journey_snapshots and audit_events."""
    # Detect dialect
    bind = getattr(conn_or_session, "bind", None) or conn_or_session
    dialect_name = getattr(bind, "dialect", None)
    name = dialect_name.name if dialect_name else ""

    if name == "postgresql":
        pg_sql = """
        CREATE OR REPLACE FUNCTION reject_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'immutable table: %', TG_TABLE_NAME; END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS no_update_snapshots ON journey_snapshots;
        CREATE TRIGGER no_update_snapshots BEFORE UPDATE OR DELETE ON journey_snapshots
          FOR EACH ROW EXECUTE FUNCTION reject_mutation();

        DROP TRIGGER IF EXISTS no_update_audit ON audit_events;
        CREATE TRIGGER no_update_audit BEFORE UPDATE OR DELETE ON audit_events
          FOR EACH ROW EXECUTE FUNCTION reject_mutation();
        """
        if hasattr(conn_or_session, "execute"):
            await conn_or_session.execute(text(pg_sql))
    elif name == "sqlite":
        sqlite_sqls = [
            """
            CREATE TRIGGER IF NOT EXISTS no_update_snapshots BEFORE UPDATE ON journey_snapshots
            BEGIN
                SELECT RAISE(ABORT, 'immutable table: journey_snapshots');
            END;
            """,
            """
            CREATE TRIGGER IF NOT EXISTS no_delete_snapshots BEFORE DELETE ON journey_snapshots
            BEGIN
                SELECT RAISE(ABORT, 'immutable table: journey_snapshots');
            END;
            """,
            """
            CREATE TRIGGER IF NOT EXISTS no_update_audit BEFORE UPDATE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'immutable table: audit_events');
            END;
            """,
            """
            CREATE TRIGGER IF NOT EXISTS no_delete_audit BEFORE DELETE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'immutable table: audit_events');
            END;
            """,
        ]
        if hasattr(conn_or_session, "execute"):
            for s in sqlite_sqls:
                await conn_or_session.execute(text(s))
