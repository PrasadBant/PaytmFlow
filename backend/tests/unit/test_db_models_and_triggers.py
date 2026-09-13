from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import (
    AuditEventModel,
    Base,
    ClarificationModel,
    EvidenceModel,
    IdempotencyKeyModel,
    JourneyModel,
    JourneySnapshotModel,
    PackMetadataModel,
    SessionModel,
)
from app.db.session import create_immutability_triggers


@pytest.fixture
async def db_session() -> AsyncSession:
    # Use SQLite in-memory for fast and isolated unit tests
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await create_immutability_triggers(conn)

    session_maker = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session

    await test_engine.dispose()


async def test_all_8_models_crud(db_session: AsyncSession):
    now = datetime.now(UTC)
    session_id = uuid4()
    journey_id = uuid4()
    snap_id = uuid4()

    # 1. SessionModel
    session_obj = SessionModel(
        id=session_id,
        created_at=now,
        expires_at=now + timedelta(days=30),
        meta={"ip": "127.0.0.1"},
    )
    db_session.add(session_obj)

    # 2. JourneyModel
    journey_obj = JourneyModel(
        id=journey_id,
        session_id=session_id,
        journey_type="LENDING",
        schema_version="1.0.0",
        status="IN_PROGRESS",
        readiness="NOT_READY",
        goal={"loan_amount": 200000},
        display_title="Personal Loan",
        display_summary="₹2,00,000",
        created_at=now,
        updated_at=now,
    )
    db_session.add(journey_obj)

    # 3. JourneySnapshotModel
    snap_obj = JourneySnapshotModel(
        id=snap_id,
        journey_id=journey_id,
        version_number=1,
        previous_snapshot_id=None,
        readiness="NOT_READY",
        fields={"monthly_income": {"status": "BLOCKED"}},
        goal={"loan_amount": 200000},
        created_at=now,
    )
    db_session.add(snap_obj)
    await db_session.flush()

    # Link current_snapshot_id
    journey_obj.current_snapshot_id = snap_id

    # 4. EvidenceModel
    evidence_obj = EvidenceModel(
        id=uuid4(),
        journey_id=journey_id,
        doc_type="SALARY_SLIP",
        filename="salary.pdf",
        file_path="/storage/salary.pdf",
        sha256="abc123sha256hash",
        file_size_bytes=1024,
        mime_type="application/pdf",
        created_at=now,
    )
    db_session.add(evidence_obj)

    # 5. ClarificationModel
    clarification_obj = ClarificationModel(
        id=uuid4(),
        journey_id=journey_id,
        ambiguity_id="INCOME_MISMATCH",
        field_key="monthly_income",
        question="Select correct income",
        answer_type="MONEY",
        created_at=now,
    )
    db_session.add(clarification_obj)

    # 6. IdempotencyKeyModel
    idempotency_obj = IdempotencyKeyModel(
        key="idemp-key-123",
        session_id=session_id,
        journey_id=journey_id,
        action_id="UPLOAD_INCOME_PROOF",
        request_hash="hash123",
        response_body={"status": "ok"},
        status_code=200,
        created_at=now,
    )
    db_session.add(idempotency_obj)

    # 7. AuditEventModel
    audit_obj = AuditEventModel(
        id=uuid4(),
        journey_id=journey_id,
        session_id=session_id,
        event_type="JOURNEY_CREATED",
        payload={"journey_id": str(journey_id)},
        created_at=now,
    )
    db_session.add(audit_obj)

    # 8. PackMetadataModel
    pack_obj = PackMetadataModel(
        journey_type="LENDING",
        schema_version="1.0.0",
        display_name="Personal Loan",
        description="Instant loan",
        icon="rupee",
        flagship_demo=True,
        updated_at=now,
    )
    db_session.add(pack_obj)

    await db_session.commit()

    # Query verification
    stmt = select(JourneyModel).where(JourneyModel.id == journey_id)
    res = await db_session.scalar(stmt)
    assert res is not None
    assert res.journey_type == "LENDING"
    assert res.current_snapshot_id == snap_id


async def test_snapshot_chain_no_forking_constraints(db_session: AsyncSession):
    now = datetime.now(UTC)
    session_id = uuid4()
    journey_id = uuid4()
    snap1_id = uuid4()

    session_obj = SessionModel(
        id=session_id,
        created_at=now,
        expires_at=now + timedelta(days=30),
    )
    journey_obj = JourneyModel(
        id=journey_id,
        session_id=session_id,
        journey_type="LENDING",
    )
    snap1 = JourneySnapshotModel(
        id=snap1_id,
        journey_id=journey_id,
        version_number=1,
        previous_snapshot_id=None,
        readiness="NOT_READY",
        fields={},
    )
    db_session.add_all([session_obj, journey_obj, snap1])
    await db_session.commit()

    # 1. Duplicate version_number must raise IntegrityError
    dup_version_snap = JourneySnapshotModel(
        id=uuid4(),
        journey_id=journey_id,
        version_number=1,  # DUPLICATE version 1
        previous_snapshot_id=None,
        readiness="NOT_READY",
        fields={},
    )
    db_session.add(dup_version_snap)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    # 2. Duplicate previous_snapshot_id (forking) must raise IntegrityError
    snap2 = JourneySnapshotModel(
        id=uuid4(),
        journey_id=journey_id,
        version_number=2,
        previous_snapshot_id=snap1_id,
        readiness="NOT_READY",
        fields={},
    )
    db_session.add(snap2)
    await db_session.commit()

    fork_snap = JourneySnapshotModel(
        id=uuid4(),
        journey_id=journey_id,
        version_number=3,
        previous_snapshot_id=snap1_id,  # FORK: already has child snap2
        readiness="NOT_READY",
        fields={},
    )
    db_session.add(fork_snap)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_snapshot_immutability_trigger_rejects_update_and_delete(db_session: AsyncSession):
    now = datetime.now(UTC)
    session_id = uuid4()
    journey_id = uuid4()
    snap_id = uuid4()

    session_obj = SessionModel(id=session_id, created_at=now, expires_at=now + timedelta(days=30))
    journey_obj = JourneyModel(id=journey_id, session_id=session_id, journey_type="LENDING")
    snap = JourneySnapshotModel(
        id=snap_id,
        journey_id=journey_id,
        version_number=1,
        previous_snapshot_id=None,
        readiness="NOT_READY",
        fields={},
    )
    db_session.add_all([session_obj, journey_obj, snap])
    await db_session.commit()

    # UPDATE on journey_snapshots must fail due to immutability trigger
    with pytest.raises((IntegrityError, DBAPIError)):
        stmt = (
            update(JourneySnapshotModel)
            .where(JourneySnapshotModel.id == snap_id)
            .values(readiness="READY")
        )
        await db_session.execute(stmt)
        await db_session.commit()
    await db_session.rollback()

    # DELETE on journey_snapshots must fail due to immutability trigger
    with pytest.raises((IntegrityError, DBAPIError)):
        await db_session.delete(snap)
        await db_session.commit()
    await db_session.rollback()


async def test_audit_event_immutability_trigger_rejects_update_and_delete(db_session: AsyncSession):
    now = datetime.now(UTC)
    session_id = uuid4()
    journey_id = uuid4()
    audit_id = uuid4()

    session_obj = SessionModel(id=session_id, created_at=now, expires_at=now + timedelta(days=30))
    journey_obj = JourneyModel(id=journey_id, session_id=session_id, journey_type="LENDING")
    audit = AuditEventModel(
        id=audit_id,
        journey_id=journey_id,
        session_id=session_id,
        event_type="JOURNEY_CREATED",
        payload={},
        created_at=now,
    )
    db_session.add_all([session_obj, journey_obj, audit])
    await db_session.commit()

    # UPDATE on audit_events must fail due to immutability trigger
    with pytest.raises((IntegrityError, DBAPIError)):
        stmt = (
            update(AuditEventModel)
            .where(AuditEventModel.id == audit_id)
            .values(event_type="TAMPERED_EVENT")
        )
        await db_session.execute(stmt)
        await db_session.commit()
    await db_session.rollback()

    # DELETE on audit_events must fail due to immutability trigger
    with pytest.raises((IntegrityError, DBAPIError)):
        await db_session.delete(audit)
        await db_session.commit()
    await db_session.rollback()
