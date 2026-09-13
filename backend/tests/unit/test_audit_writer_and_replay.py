from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.audit import AuditEventType, AuditWriter, replay_journey
from app.core.models import CoreFieldStatus, CoreReadiness
from app.db.models import Base
from app.db.repositories import AuditRepository, SessionRepository
from app.db.session import create_immutability_triggers
from app.packs.registry import pack_registry
from app.schemas.enums import JourneyType


@pytest.fixture
async def db_session() -> AsyncSession:
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await create_immutability_triggers(conn)

    session_maker = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session

    await test_engine.dispose()


async def test_audit_writer_all_7_event_types(db_session: AsyncSession):
    session_repo = SessionRepository(db_session)
    audit_repo = AuditRepository(db_session)
    writer = AuditWriter(audit_repo)

    now = datetime.now(UTC)
    sess = await session_repo.create(expires_at=now + timedelta(days=30))
    journey_id = uuid4()
    snap1_id = uuid4()
    snap2_id = uuid4()
    token_id = uuid4()
    evidence_id = uuid4()
    clarification_id = uuid4()

    # 1. JOURNEY_CREATED
    e1 = await writer.record_journey_created(
        journey_id=journey_id,
        session_id=sess.id,
        journey_type="LENDING",
        goal={"loan_amount": 200000},
        initial_snapshot_id=snap1_id,
        initial_values={"kyc_verified": True},
    )
    assert e1.event_type == AuditEventType.JOURNEY_CREATED

    # 2. ACTION_EXECUTED
    e2 = await writer.record_action_executed(
        journey_id=journey_id,
        session_id=sess.id,
        action_id="UPLOAD_INCOME_PROOF",
        token_id=token_id,
        snapshot_id=snap2_id,
        version_number=2,
        action_input={"monthly_income": 85000},
        new_values={"monthly_income": 85000},
    )
    assert e2.event_type == AuditEventType.ACTION_EXECUTED

    # 3. ACTION_REJECTED
    e3 = await writer.record_action_rejected(
        journey_id=journey_id,
        session_id=sess.id,
        action_id="ACCEPT_LOAN_TERMS",
        reason="Preconditions not met",
        error_code="ACTION_INVALID",
    )
    assert e3.event_type == AuditEventType.ACTION_REJECTED

    # 4. EVIDENCE_UPLOADED
    e4 = await writer.record_evidence_uploaded(
        journey_id=journey_id,
        session_id=sess.id,
        evidence_id=evidence_id,
        doc_type="SALARY_SLIP",
        filename="slip.pdf",
        sha256="sha256_hash",
        confidence=0.92,
    )
    assert e4.event_type == AuditEventType.EVIDENCE_UPLOADED

    # 5. CLARIFICATION_REQUESTED
    e5 = await writer.record_clarification_requested(
        journey_id=journey_id,
        session_id=sess.id,
        ambiguity_id="INCOME_MISMATCH",
        field_key="monthly_income",
        question="Select your net income",
    )
    assert e5.event_type == AuditEventType.CLARIFICATION_REQUESTED

    # 6. CLARIFICATION_ANSWERED
    e6 = await writer.record_clarification_answered(
        journey_id=journey_id,
        session_id=sess.id,
        clarification_id=clarification_id,
        ambiguity_id="INCOME_MISMATCH",
        field_key="monthly_income",
        user_response={"monthly_income": 85000},
        snapshot_id=uuid4(),
    )
    assert e6.event_type == AuditEventType.CLARIFICATION_ANSWERED

    # 7. STATE_TRANSITION
    e7 = await writer.record_state_transition(
        journey_id=journey_id,
        session_id=sess.id,
        from_readiness="NOT_READY",
        to_readiness="READY",
        from_status="IN_PROGRESS",
        to_status="COMPLETED",
        snapshot_id=snap2_id,
    )
    assert e7.event_type == AuditEventType.STATE_TRANSITION

    # Verify all 7 persisted
    events = await audit_repo.list_by_journey_id(journey_id)
    assert len(events) == 7


async def test_audit_replay_reconstructs_state_exact(db_session: AsyncSession):
    pack_registry.load_all()
    lending_manifest = pack_registry.get_pack(JourneyType.LENDING)
    assert lending_manifest is not None

    session_repo = SessionRepository(db_session)
    audit_repo = AuditRepository(db_session)
    writer = AuditWriter(audit_repo)

    now = datetime.now(UTC)
    sess = await session_repo.create(expires_at=now + timedelta(days=30))
    journey_id = uuid4()
    snap1_id = uuid4()
    snap2_id = uuid4()
    snap3_id = uuid4()
    snap4_id = uuid4()
    snap5_id = uuid4()

    # Sequence of events leading to READY:
    # 1. JOURNEY_CREATED (v1)
    await writer.record_journey_created(
        journey_id=journey_id,
        session_id=sess.id,
        journey_type="LENDING",
        goal={"loan_amount": 200000, "tenure_months": 24},
        initial_snapshot_id=snap1_id,
        initial_values={
            "kyc_verified": True,
            "pan_validated": "ABCDE1234F",
            "bank_account_linked": "HDFC0001234",
        },
    )

    # 2. EVIDENCE_UPLOADED (informational audit event, doesn't change snapshot)
    await writer.record_evidence_uploaded(
        journey_id=journey_id,
        session_id=sess.id,
        evidence_id=uuid4(),
        doc_type="SALARY_SLIP",
        filename="salary.pdf",
        sha256="abc123sha",
        confidence=0.92,
    )

    # 3. ACTION_EXECUTED UPLOAD_INCOME_PROOF (v2)
    await writer.record_action_executed(
        journey_id=journey_id,
        session_id=sess.id,
        action_id="UPLOAD_INCOME_PROOF",
        token_id=uuid4(),
        snapshot_id=snap2_id,
        version_number=2,
        action_input={"monthly_income": 85000},
        new_values={"monthly_income": 85000},
    )

    # 4. ACTION_REJECTED (rejection audit event, doesn't change state)
    await writer.record_action_rejected(
        journey_id=journey_id,
        session_id=sess.id,
        action_id="ACCEPT_LOAN_TERMS",
        reason="Preconditions not met",
        error_code="ACTION_INVALID",
    )

    # 5. ACTION_EXECUTED SUBMIT_EMPLOYMENT_INFO (v3)
    await writer.record_action_executed(
        journey_id=journey_id,
        session_id=sess.id,
        action_id="SUBMIT_EMPLOYMENT_INFO",
        token_id=uuid4(),
        snapshot_id=snap3_id,
        version_number=3,
        action_input={"employment_type": "SALARIED"},
        new_values={"employment_type": "SALARIED"},
    )

    # 6. ACTION_EXECUTED VERIFY_EMPLOYER_RECORD (v4)
    await writer.record_action_executed(
        journey_id=journey_id,
        session_id=sess.id,
        action_id="VERIFY_EMPLOYER_RECORD",
        token_id=uuid4(),
        snapshot_id=snap4_id,
        version_number=4,
        action_input={"employer_name": "Acme Inc"},
        new_values={"employer_name": "Acme Inc"},
    )

    # 7. ACTION_EXECUTED ACCEPT_LOAN_TERMS (v5)
    await writer.record_action_executed(
        journey_id=journey_id,
        session_id=sess.id,
        action_id="ACCEPT_LOAN_TERMS",
        token_id=uuid4(),
        snapshot_id=snap5_id,
        version_number=5,
        action_input={"accept_terms": True},
        new_values={"loan_offer_accepted": True},
    )

    events = await audit_repo.list_by_journey_id(journey_id)
    assert len(events) == 7

    # Replay state from audit log
    replayed_snap = replay_journey(
        journey_id=journey_id,
        events=events,
        manifest=lending_manifest,
    )

    assert replayed_snap.journey_id == journey_id
    assert replayed_snap.snapshot_id == snap5_id
    assert replayed_snap.version_number == 5
    assert replayed_snap.readiness == CoreReadiness.READY

    # Verify all 7 mandatory fields are satisfied
    assert replayed_snap.fields["kyc_verified"].status == CoreFieldStatus.SATISFIED
    assert replayed_snap.fields["pan_validated"].status == CoreFieldStatus.SATISFIED
    assert replayed_snap.fields["bank_account_linked"].status == CoreFieldStatus.SATISFIED
    assert replayed_snap.fields["monthly_income"].value == 85000
    assert replayed_snap.fields["monthly_income"].status == CoreFieldStatus.SATISFIED
    assert replayed_snap.fields["employment_type"].value == "SALARIED"
    assert replayed_snap.fields["employment_type"].status == CoreFieldStatus.SATISFIED
    assert replayed_snap.fields["employer_name"].value == "Acme Inc"
    assert replayed_snap.fields["employer_name"].status == CoreFieldStatus.SATISFIED
    assert replayed_snap.fields["loan_offer_accepted"].value is True
    assert replayed_snap.fields["loan_offer_accepted"].status == CoreFieldStatus.SATISFIED


async def test_audit_replay_with_clarifications(db_session: AsyncSession):
    pack_registry.load_all()
    lending_manifest = pack_registry.get_pack(JourneyType.LENDING)
    assert lending_manifest is not None

    session_repo = SessionRepository(db_session)
    audit_repo = AuditRepository(db_session)
    writer = AuditWriter(audit_repo)

    now = datetime.now(UTC)
    sess = await session_repo.create(expires_at=now + timedelta(days=30))
    journey_id = uuid4()
    snap1_id = uuid4()
    snap2_id = uuid4()

    # 1. JOURNEY_CREATED
    await writer.record_journey_created(
        journey_id=journey_id,
        session_id=sess.id,
        journey_type="LENDING",
        goal={"loan_amount": 200000},
        initial_snapshot_id=snap1_id,
        initial_values={
            "kyc_verified": True,
            "pan_validated": "ABCDE1234F",
            "bank_account_linked": "HDFC0001234",
            "monthly_income": 62000,
        },
    )

    # 2. CLARIFICATION_REQUESTED on monthly_income
    await writer.record_clarification_requested(
        journey_id=journey_id,
        session_id=sess.id,
        ambiguity_id="INCOME_MISMATCH",
        field_key="monthly_income",
        question="Select correct monthly income",
    )

    events_mid = await audit_repo.list_by_journey_id(journey_id)
    replayed_mid = replay_journey(journey_id, events_mid, lending_manifest)
    assert replayed_mid.readiness == CoreReadiness.NEEDS_REVIEW
    assert replayed_mid.fields["monthly_income"].status == CoreFieldStatus.AMBIGUOUS
    assert replayed_mid.pending_clarification is not None

    # 3. CLARIFICATION_ANSWERED
    await writer.record_clarification_answered(
        journey_id=journey_id,
        session_id=sess.id,
        clarification_id=uuid4(),
        ambiguity_id="INCOME_MISMATCH",
        field_key="monthly_income",
        user_response={"monthly_income": 85000},
        snapshot_id=snap2_id,
    )

    events_final = await audit_repo.list_by_journey_id(journey_id)
    replayed_final = replay_journey(journey_id, events_final, lending_manifest)
    assert replayed_final.fields["monthly_income"].status == CoreFieldStatus.SATISFIED
    assert replayed_final.fields["monthly_income"].value == 85000
    assert replayed_final.pending_clarification is None
    assert replayed_final.version_number == 2
    assert replayed_final.snapshot_id == snap2_id
