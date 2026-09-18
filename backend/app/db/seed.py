import asyncio
import os
import shutil
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import SessionModel
from app.db.session import async_session_factory, create_immutability_triggers
from app.packs.registry import pack_registry
from app.schemas.enums import JourneyType
from app.services.journey_service import JourneyService

DEMO_SESSION_ID = UUID("00000000-0000-0000-0000-000000000001")


async def clear_database_tables(session: AsyncSession) -> None:
    """Wipe all user and journey data while respecting or temporarily lifting triggers."""
    bind = getattr(session, "bind", None) or session
    dialect_name = getattr(bind, "dialect", None)
    name = dialect_name.name if dialect_name else ""

    if name == "postgresql":
        await session.execute(
            text(
                "TRUNCATE TABLE audit_events, idempotency_keys, evidence, "
                "clarifications, journey_snapshots, journeys, sessions CASCADE;"
            )
        )
    else:
        # SQLite
        await session.execute(text("DROP TRIGGER IF EXISTS no_update_snapshots;"))
        await session.execute(text("DROP TRIGGER IF EXISTS no_delete_snapshots;"))
        await session.execute(text("DROP TRIGGER IF EXISTS no_update_audit;"))
        await session.execute(text("DROP TRIGGER IF EXISTS no_delete_audit;"))
        await session.execute(text("PRAGMA foreign_keys = OFF;"))
        await session.execute(text("DELETE FROM audit_events;"))
        await session.execute(text("DELETE FROM idempotency_keys;"))
        await session.execute(text("DELETE FROM evidence;"))
        await session.execute(text("DELETE FROM clarifications;"))
        await session.execute(text("DELETE FROM journey_snapshots;"))
        await session.execute(text("DELETE FROM journeys;"))
        await session.execute(text("DELETE FROM sessions;"))
        await session.execute(text("PRAGMA foreign_keys = ON;"))
        await create_immutability_triggers(session)

    await session.commit()
    session.expire_all()


def clear_evidence_storage() -> None:
    """Clean uploaded evidence storage files."""
    storage_dir = settings.EVIDENCE_STORAGE_DIR
    if os.path.exists(storage_dir):
        for item in os.listdir(storage_dir):
            item_path = os.path.join(storage_dir, item)
            try:
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    os.unlink(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            except Exception:
                pass


async def seed_demo_data(session: AsyncSession) -> None:
    """Seed default demo session and initial golden showcase journeys for Screen 10."""
    pack_registry.load_all()

    # 1. Create default demo session
    demo_session = await session.get(SessionModel, DEMO_SESSION_ID)
    if not demo_session:
        demo_session = SessionModel(
            id=DEMO_SESSION_ID,
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=settings.SESSION_TTL_DAYS),
            meta={"source": "demo_seed", "role": "demo_user"},
        )
        session.add(demo_session)
        await session.commit()

    # 2. Seed showcase journeys across all 6 packs
    await JourneyService.create_journey(
        session=demo_session,
        journey_type=JourneyType.LENDING,
        goal={
            "loan_amount": 250000,
            "loan_purpose": "HOME_RENOVATION",
            "tenure_months": 24,
        },
        natural_language=None,
        db=session,
    )

    await JourneyService.create_journey(
        session=demo_session,
        journey_type=JourneyType.INSURANCE,
        goal={
            "policy_type": "INDIVIDUAL",
            "sum_insured": 500000,
        },
        natural_language=None,
        db=session,
    )

    await JourneyService.create_journey(
        session=demo_session,
        journey_type=JourneyType.CREDIT_CARD,
        goal={
            "card_variant": "CASHBACK",
            "credit_limit_preference": 100000,
        },
        natural_language=None,
        db=session,
    )

    await JourneyService.create_journey(
        session=demo_session,
        journey_type=JourneyType.KYC,
        goal={
            "kyc_purpose": "PERIODIC_UPDATE",
        },
        natural_language=None,
        db=session,
    )

    await JourneyService.create_journey(
        session=demo_session,
        journey_type=JourneyType.ACCOUNT_OPENING,
        goal={
            "account_type": "DIGITAL_SAVINGS",
            "initial_deposit": 10000,
        },
        natural_language=None,
        db=session,
    )

    await JourneyService.create_journey(
        session=demo_session,
        journey_type=JourneyType.INVESTMENT,
        goal={
            "investment_mode": "MONTHLY_SIP",
            "target_amount": 5000,
        },
        natural_language=None,
        db=session,
    )


async def reset_demo_state(db: AsyncSession | None = None) -> int:
    """Wipes journey data, clears evidence storage, and re-seeds demo journeys.

    Returns:
        elapsed_ms: execution time in milliseconds.
    """
    start_time = time.perf_counter()

    clear_evidence_storage()

    if db is not None:
        await clear_database_tables(db)
        await seed_demo_data(db)
    else:
        async with async_session_factory() as session:
            await clear_database_tables(session)
            await seed_demo_data(session)

    elapsed_ms = max(1, int((time.perf_counter() - start_time) * 1000))
    return elapsed_ms


def main() -> None:
    elapsed = asyncio.run(reset_demo_state())
    print(f"Demo reset complete in {elapsed}ms.")


if __name__ == "__main__":
    main()
